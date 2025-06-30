from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from labelme.dlcv.app import MainWindow


class Store:
    edit_label_name: callable = None
    canvas_display_shape_label: bool = True
    convert_img_to_gray: bool = False
    canvas_highlight_start_point: bool = False
    canvas_display_rotation_arrow = False  # 是否显示旋转框箭头
    canvas_brush_enabled: bool = False  # 是否启用画笔标注
    canvas_brush_size: int = 10  # 画笔大小
    canvas_brush_fill_region: bool = True  # 是否填充闭合区域
    canvas_brush_modify_shapes: bool = True  # 是否允许画笔修改现有形状

    auto_label_covered: bool = False

    # main window
    __main_window: 'MainWindow' = None

    def set_edit_label_name(self, edit_label: callable):
        assert callable(edit_label)
        self.edit_label_name = edit_label

    def set_canvas_display_shape_label(self, display: bool):
        assert isinstance(display, bool)
        self.canvas_display_shape_label = display

    def set_convert_img_to_gray(self, convert: bool):
        self.convert_img_to_gray = convert

    def set_canvas_highlight_start_point(self, highlight: bool):
        assert isinstance(highlight, bool)
        self.canvas_highlight_start_point = highlight

    def set_canvas_display_rotation_arrow(self, value: bool):
        self.canvas_display_rotation_arrow = value
        
    def set_canvas_brush_enabled(self, value: bool):
        self.canvas_brush_enabled = value
        
    def set_canvas_brush_size(self, value: int):
        self.canvas_brush_size = value
        self.main_window.parameter.child("label_setting", "brush_size").setValue(
            value
        )
        
    def set_canvas_brush_fill_region(self, value: bool):
        self.canvas_brush_fill_region = value

    def set_canvas_brush_modify_shapes(self, value: bool):
        self.canvas_brush_modify_shapes = value

    # 注册 main_window 以供全局访问
    def register_main_window(self, main_window: 'MainWindow'):
        self.__main_window = main_window

    def get_config(self):
        return self.__main_window._config

    # 需要先register_main_window,才能访问main_window
    @property
    def main_window(self) -> 'MainWindow':
        assert self.__main_window is not None
        return self.__main_window


# 创建一个全局的store对象
STORE = Store()

if __name__ == '__main__':
    STORE.register_main_window(123)
    STORE.main_window
