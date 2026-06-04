from typing import TYPE_CHECKING

from qtpy import QtCore

if TYPE_CHECKING:
    from labelme.dlcv.app import MainWindow


class Store:
    """全局运行时状态容器。

    对于在设置面板（ParameterTree）中有对应项的配置，直接代理到 parameter 读取，
    不再维护本地副本，避免双份数据同步问题。
    """

    # ---------- 无 Parameter 对应项的运行时状态 ----------
    edit_label_name: callable = None
    canvas_brush_enabled: bool = False  # 画笔是否启用（运行时状态，无持久化 UI）
    canvas_brush_modify_shapes: bool = True  # 是否允许画笔修改现有形状（无持久化 UI）
    auto_label_covered: bool = False

    # main window
    __main_window: "MainWindow" = None
    q_translator: QtCore.QTranslator = None

    # WebSocket 连接（全局共享）
    backend_ws = None

    # ---------- Parameter 代理属性 ----------

    def _param(self, *path):
        """快捷访问 parameter 子节点。"""
        p = self.main_window.parameter
        for name in path:
            p = p.child(name)
        return p

    @property
    def canvas_display_shape_label(self) -> bool:
        return self._param("other_setting", "display_shape_label").value()

    @property
    def canvas_shape_label_font_size(self) -> int:
        return self._param("other_setting", "shape_label_font_size").value()

    @property
    def canvas_shape_label_position(self) -> str:
        """返回内部英文值：center / top_left / bottom_right"""
        from labelme.dlcv.widget.setting_dock import LabelPositionEnum, dlcv_tr

        val = self._param("other_setting", "shape_label_position").value()
        if val == dlcv_tr(LabelPositionEnum.TOP_LEFT):
            return LabelPositionEnum.TOP_LEFT
        elif val == dlcv_tr(LabelPositionEnum.BOTTOM_RIGHT):
            return LabelPositionEnum.BOTTOM_RIGHT
        return LabelPositionEnum.CENTER

    @property
    def convert_img_to_gray(self) -> bool:
        return self._param("other_setting", "convert_img_to_gray").value()

    @property
    def canvas_highlight_start_point(self) -> bool:
        return self._param("label_setting", "highlight_start_point").value()

    @property
    def canvas_display_rotation_arrow(self) -> bool:
        return self._param("label_setting", "display_rotation_arrow").value()

    @property
    def canvas_brush_size(self) -> int:
        return self._param("label_setting", "brush_size").value()

    @property
    def canvas_brush_fill_region(self) -> bool:
        return self._param("label_setting", "fill_closed_region").value()

    @property
    def canvas_points_to_crosshair(self) -> bool:
        return self._param("other_setting", "points_to_crosshair").value()

    @property
    def ai_polygon_simplify_epsilon(self):
        return self._param("label_setting", "ai_polygon_simplify_epsilon").value()

    # ---------- 保留的 setter（有额外逻辑或反向同步） ----------

    def set_edit_label_name(self, edit_label: callable):
        assert callable(edit_label)
        self.edit_label_name = edit_label

    def set_canvas_brush_enabled(self, value: bool):
        self.canvas_brush_enabled = value

    def set_canvas_brush_size(self, value: int):
        """从画布快捷键 +/- 调整画笔大小时，反向同步到设置面板。"""
        self._param("label_setting", "brush_size").setValue(value)

    def set_canvas_brush_modify_shapes(self, value: bool):
        self.canvas_brush_modify_shapes = value

    # ---------- main_window 注册 ----------

    def register_main_window(self, main_window: "MainWindow"):
        self.__main_window = main_window

    def get_config(self):
        return self.__main_window._config

    @property
    def main_window(self) -> "MainWindow":
        assert self.__main_window is not None
        return self.__main_window


# 创建一个全局的 store 对象
STORE = Store()
