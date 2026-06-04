import logging

from qtpy import QtCore, QtWidgets, QtGui
from pyqtgraph.parametertree import Parameter, ParameterTree
from pyqttoast import ToastPreset

from labelme.dlcv import dlcv_tr
from labelme.dlcv.ai import MODELS
from labelme.dlcv.store import STORE
from labelme.dlcv.utils_func import notification
from labelme.dlcv.shape import Shape

logger = logging.getLogger(__name__)


class ProjEnum:
    NORMAL = "2D"
    O2_5D = "2.5D"
    O3D = "3D"


class ScaleEnum:
    KEEP_PREV_SCALE = "保持上次缩放比例"
    AUTO_SCALE = "自动缩放"
    KEEP_SCALE = "保持缩放比例"


class LabelPositionEnum:
    CENTER = "center"
    TOP_LEFT = "top_left"
    BOTTOM_RIGHT = "bottom_right"


class SettingDock(QtWidgets.QDockWidget):
    """右侧设置面板组件，封装 ParameterTree、AI 模型选择及设置恢复/保存逻辑。"""

    def __init__(self, parent, config, canvas):
        super().__init__(dlcv_tr("setting dock"), parent)
        self._config = config
        self._canvas = canvas

        self._parameter = None
        self.parameter_tree = None
        self._selectAiModelComboBox = None

        self._init_parameter_tree()
        self._init_ai_model_combo()
        self._assemble_ui()

    # region properties
    @property
    def parameter(self):
        return self._parameter

    @property
    def selectAiModelComboBox(self):
        return self._selectAiModelComboBox

    # endregion

    # region UI 构建
    def _build_param_kwargs(self):
        """构建 pyqtgraph Parameter 的配置字典。"""
        kwargs = [
            {
                "name": "proj_setting",
                "title": dlcv_tr("project setting"),
                "type": "group",
                "children": [
                    {
                        "name": "proj_type",
                        "title": dlcv_tr("project type"),
                        "type": "list",
                        "limits": [ProjEnum.NORMAL, ProjEnum.O2_5D, ProjEnum.O3D],
                        "default": ProjEnum.NORMAL,
                    },
                ],
            },
            {
                "name": "other_setting",
                "title": dlcv_tr("other setting"),
                "type": "group",
                "children": [
                    {
                        "name": "display_shape_label",
                        "title": dlcv_tr("display shape label"),
                        "type": "bool",
                        "value": True,
                        "default": True,
                        "shortcut": self._config["shortcuts"]["display_shape_label"],
                    },
                    {
                        "name": "shape_label_font_size",
                        "title": dlcv_tr("shape label font size"),
                        "type": "int",
                        "value": 8,
                        "default": 8,
                        "min": 1,
                        "max": 20,
                        "step": 1,
                    },
                    {
                        "name": "shape_label_position",
                        "title": dlcv_tr("shape label position"),
                        "type": "list",
                        "value": dlcv_tr(LabelPositionEnum.CENTER),
                        "limits": [
                            dlcv_tr(LabelPositionEnum.CENTER),
                            dlcv_tr(LabelPositionEnum.TOP_LEFT),
                            dlcv_tr(LabelPositionEnum.BOTTOM_RIGHT),
                        ],
                        "default": dlcv_tr(LabelPositionEnum.CENTER),
                    },
                    {
                        "name": "scale_option",
                        "title": dlcv_tr("keep prev scale"),
                        "type": "list",
                        "value": dlcv_tr(ScaleEnum.AUTO_SCALE),
                        "limits": [
                            dlcv_tr(ScaleEnum.KEEP_PREV_SCALE),
                            dlcv_tr(ScaleEnum.AUTO_SCALE),
                            dlcv_tr(ScaleEnum.KEEP_SCALE),
                        ],
                        "default": dlcv_tr(ScaleEnum.AUTO_SCALE),
                    },
                    {
                        "name": "convert_img_to_gray",
                        "title": dlcv_tr("convert img to gray"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "points_to_crosshair",
                        "title": dlcv_tr("points to crosshair"),
                        "type": "bool",
                        "value": True,
                        "default": True,
                        "tip": dlcv_tr("启用后，将点转换为十字线"),
                    },
                ],
            },
            {
                "name": "label_setting",
                "title": dlcv_tr("label setting"),
                "type": "group",
                "children": [
                    {
                        "name": "blue_line_color",
                        "title": dlcv_tr("蓝色线段标注"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                        "tip": dlcv_tr("启用后，将高亮标注线段为蓝色"),
                    },
                    {
                        "name": "slide_label",
                        "title": dlcv_tr("slide label"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                        "shortcut": self._config["shortcuts"]["canvas_auto_left_click"],
                        "tip": dlcv_tr("启用滑动标注将禁用画笔标注功能，两者互斥"),
                    },
                    {
                        "name": "slide_distance",
                        "title": dlcv_tr("slide distance"),
                        "type": "int",
                        "value": 30,
                        "default": 30,
                    },
                    {
                        "name": "fill_closed_region",
                        "title": dlcv_tr("fill closed region"),
                        "type": "bool",
                        "value": True,
                        "default": True,
                        "tip": dlcv_tr("启用后，闭合区域内部将被填充，否则仅保留轮廓"),
                    },
                    {
                        "name": "brush_size",
                        "title": dlcv_tr("brush size"),
                        "type": "int",
                        "value": 3,
                        "default": 3,
                        "min": 2,
                    },
                    {
                        "name": "highlight_start_point",
                        "title": dlcv_tr("highlight start point"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "display_rotation_arrow",
                        "title": dlcv_tr("显示旋转框箭头与角度"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "ai_polygon_simplify_epsilon",
                        "title": dlcv_tr("AI多边形点数简化设置"),
                        "type": "float",
                        "value": 0.005,
                        "default": 0.005,
                        "min": 0.001,
                        "max": 0.1,
                        "step": 0.005,
                        "tip": dlcv_tr(
                            "简化程度说明：\n0.001: 轻微简化\n0.005: 默认简化\n0.01: 较多简化\n0.05: 大量简化\n0.1: 极度简化"
                        ),
                    },
                ],
            },
            {
                "name": "auto_setting",
                "title": dlcv_tr("auto setting"),
                "type": "group",
                "children": [
                    {
                        "name": "use_bbox",
                        "title": dlcv_tr("使用Bbox进行自动标注"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "category_filter_list",
                        "title": dlcv_tr("请输入需要自动标注的类别"),
                        "type": "text",
                        "placeholder": dlcv_tr(
                            "请输入需要自动标注的类别，多个类别用,或，隔开"
                        ),
                        "value": "",
                        "tip": dlcv_tr("请输入需要自动标注的类别，多个类别用,或，隔开"),
                    },
                ],
            },
        ]

        # 快捷键提示文本
        for kwarg in kwargs:
            if kwarg.get("type") == "group":
                for child in kwarg.get("children", []):
                    shortcut = child.get("shortcut")
                    if shortcut:
                        child["title"] = child["title"] + f"({shortcut})"
        return kwargs

    def _init_parameter_tree(self):
        """初始化 ParameterTree 及快捷键绑定。"""
        param_kwargs = self._build_param_kwargs()
        self._parameter = Parameter.create(
            name="params", type="group", children=param_kwargs
        )
        self.parameter_tree = ParameterTree(showHeader=False)
        self.parameter_tree.setObjectName("settingParameterTree")
        self.parameter_tree.setParameters(self._parameter, showTop=False)
        self._parameter.sigTreeStateChanged.connect(self._on_param_changed)

        # 绑定快捷键 action
        for parent_kwarg in param_kwargs:
            for child in parent_kwarg.get("children", []):
                shortcut = child.get("shortcut")
                child_type = child.get("type")
                if not shortcut:
                    continue
                action = QtWidgets.QAction(self)
                action.setShortcut(shortcut)
                parameter = self._parameter.child(
                    parent_kwarg["name"], child["name"]
                )
                if child_type == "bool":
                    action.triggered.connect(
                        lambda _, p=parameter: p.setValue(not p.value())
                    )
                elif child_type == "action":
                    action.triggered.connect(lambda _, p=parameter: p.trigger())
                else:
                    raise ValueError(f"不支持的类型: {child_type}")
                self.addAction(action)

    def _init_ai_model_combo(self):
        """在设置面板顶部添加 AI Mask Model 选择器。"""
        ai_model_widget = QtWidgets.QWidget(self)
        ai_model_layout = QtWidgets.QHBoxLayout(ai_model_widget)
        ai_model_layout.setContentsMargins(6, 6, 6, 6)
        ai_model_layout.setSpacing(6)
        ai_model_label = QtWidgets.QLabel(self.tr("AI Mask Model"), ai_model_widget)
        ai_model_layout.addWidget(ai_model_label)

        self._selectAiModelComboBox = QtWidgets.QComboBox(ai_model_widget)
        self._selectAiModelComboBox.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        model_names = [model.name for model in MODELS]
        self._selectAiModelComboBox.addItems(model_names)
        if self._config["ai"]["default"] in model_names:
            model_index = model_names.index(self._config["ai"]["default"])
        else:
            logger.warning(
                "Default AI model is not found: %r",
                self._config["ai"]["default"],
            )
            model_index = 0
        self._selectAiModelComboBox.setCurrentIndex(model_index)
        self._selectAiModelComboBox.currentIndexChanged.connect(
            lambda: self._canvas.initializeAiModel(
                name=self._selectAiModelComboBox.currentText()
            )
            if self._canvas.createMode in ["ai_polygon", "ai_mask"]
            else None
        )
        ai_model_layout.addWidget(self._selectAiModelComboBox, 1)
        return ai_model_widget

    def _assemble_ui(self):
        """把 AI 模型选择器和 ParameterTree 组装到 DockWidget 中。"""
        ai_model_widget = self._init_ai_model_combo()

        setting_container = QtWidgets.QWidget(self)
        setting_container.setObjectName("settingPanel")
        setting_layout = QtWidgets.QVBoxLayout(setting_container)
        setting_layout.setContentsMargins(8, 8, 8, 8)
        setting_layout.setSpacing(6)
        setting_layout.addWidget(ai_model_widget)

        line = QtWidgets.QFrame(setting_container)
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        setting_layout.addWidget(line)
        setting_layout.addWidget(self.parameter_tree)

        self.setWidget(setting_container)
        self.setObjectName("setting_dock")

    def _on_param_changed(self, param, changes):
        """参数变更回调：处理所有设置变更逻辑。"""
        mw = STORE.main_window
        for param, _, new_value in changes:
            path = self._parameter.childPath(param)
            parent_path = path[:-1]
            param_name = path[-1]

            if len(parent_path) == 1 and parent_path[0] == "label_setting":
                if param_name == "blue_line_color":
                    if new_value:
                        Shape.line_color = QtGui.QColor(0, 127, 255, 255)
                        Shape.vertex_fill_color = QtGui.QColor(0, 127, 255, 255)
                    else:
                        Shape.line_color = QtGui.QColor(0, 255, 0, 128)
                        Shape.vertex_fill_color = QtGui.QColor(0, 255, 0, 255)

                elif param_name == "slide_label":
                    mw.draw_polygon_with_mousemove = new_value
                    self._canvas.draw_polygon_with_mousemove = new_value
                    if new_value and self._canvas.brush_enabled:
                        self._canvas.brush_enabled = False
                        STORE.set_canvas_brush_enabled(False)
                        notification(
                            dlcv_tr("功能互斥"),
                            dlcv_tr("已禁用画笔标注功能"),
                            ToastPreset.INFORMATION,
                        )

                elif param_name == "slide_distance":
                    self._canvas.two_points_distance = new_value
                elif param_name == "brush_size":
                    self._canvas.brush_size = new_value

            elif len(parent_path) == 1 and parent_path[0] == "other_setting":
                if param_name in (
                    "display_shape_label",
                    "shape_label_font_size",
                    "shape_label_position",
                    "points_to_crosshair",
                ):
                    self._canvas.update()
                elif param_name == "scale_option":
                    if new_value == dlcv_tr(ScaleEnum.KEEP_PREV_SCALE):
                        mw.enableKeepPrevScale(True)
                    elif new_value == dlcv_tr(ScaleEnum.AUTO_SCALE):
                        mw.enableKeepPrevScale(False)
                    elif new_value == dlcv_tr(ScaleEnum.KEEP_SCALE):
                        mw.enableKeepPrevScale(False)

    # endregion

    # region 恢复 / 保存
    def restore_settings(self, settings):
        """从 QSettings 中恢复设置面板的状态。"""
        setting_store = settings.value("setting_store", None)
        if not setting_store:
            return

        self._parameter.child("other_setting", "display_shape_label").setValue(
            setting_store.get("display_shape_label", True)
        )
        self._parameter.child("other_setting", "convert_img_to_gray").setValue(
            setting_store.get("convert_img_to_gray", False)
        )
        self._parameter.child("other_setting", "shape_label_font_size").setValue(
            setting_store.get("shape_label_font_size", 8)
        )

        # 标签显示位置（兼容旧数据：可能是中文翻译值或英文值）
        saved_pos = setting_store.get("shape_label_position", LabelPositionEnum.CENTER)
        if saved_pos in (LabelPositionEnum.CENTER, dlcv_tr(LabelPositionEnum.CENTER)):
            display_pos = dlcv_tr(LabelPositionEnum.CENTER)
        elif saved_pos in (LabelPositionEnum.TOP_LEFT, dlcv_tr(LabelPositionEnum.TOP_LEFT)):
            display_pos = dlcv_tr(LabelPositionEnum.TOP_LEFT)
        elif saved_pos in (LabelPositionEnum.BOTTOM_RIGHT, dlcv_tr(LabelPositionEnum.BOTTOM_RIGHT)):
            display_pos = dlcv_tr(LabelPositionEnum.BOTTOM_RIGHT)
        else:
            display_pos = dlcv_tr(LabelPositionEnum.CENTER)
        self._parameter.child("other_setting", "shape_label_position").setValue(display_pos)

        self._parameter.child("other_setting", "points_to_crosshair").setValue(
            setting_store.get("canvas_points_to_crosshair", True)
        )
        self._parameter.child("label_setting", "highlight_start_point").setValue(
            setting_store.get("highlight_start_point", False)
        )
        self._parameter.child(
            "label_setting", "display_rotation_arrow"
        ).setValue(setting_store.get("canvas_display_rotation_arrow", True))
        self._parameter.child("label_setting", "fill_closed_region").setValue(
            setting_store.get("canvas_brush_fill_region", True)
        )
        self._parameter.child("other_setting", "scale_option").setValue(
            setting_store.get("scale_option", dlcv_tr(ScaleEnum.AUTO_SCALE))
        )
        self._parameter.child(
            "label_setting", "ai_polygon_simplify_epsilon"
        ).setValue(setting_store.get("ai_polygon_simplify_epsilon", 0.005))

    def save_settings(self):
        """返回需要从 QSettings 保存的参数值字典。"""
        return {
            "scale_option": self._parameter.child(
                "other_setting", "scale_option"
            ).value(),
            "ai_polygon_simplify_epsilon": self._parameter.child(
                "label_setting", "ai_polygon_simplify_epsilon"
            ).value(),
        }

    # endregion
