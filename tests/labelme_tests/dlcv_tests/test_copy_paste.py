import copy
from types import SimpleNamespace

import pytest

from labelme.dlcv.controller import copy_paste as controller
from labelme.dlcv.utils import copy_paste


class Point:
    def __init__(self, x, y):
        self._x = float(x)
        self._y = float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def setX(self, value):
        self._x = float(value)

    def setY(self, value):
        self._y = float(value)


class Shape:
    def __init__(self, points, shape_type="polygon"):
        self.points = [Point(x, y) for x, y in points]
        self.shape_type = shape_type
        self.selected = True

    def copy(self):
        return copy.deepcopy(self)


class Action:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, value):
        self.enabled = value


class Window(controller.CopyPasteMixin):
    def __init__(self, shapes):
        self.canvas = SimpleNamespace(
            selectedShapes=shapes,
            shapes=[],
            prevMovePoint=Point(50, 40),
            selectShapes=lambda selected: setattr(self, "selected", selected),
            storeShapes=lambda: None,
            update=lambda: None,
        )
        self.actions = SimpleNamespace(paste=Action())
        self.imagePath = "C:/data/a.png"
        self.filename = self.imagePath
        self._copied_shapes = None
        self._copied_shapes_source = ""
        self._same_image_paste_count = 0
        self.loaded = []
        self.dirty = False

    @property
    def max_x_width(self):
        return 99.999

    @property
    def max_y_height(self):
        return 79.999

    def loadShapes(self, shapes, replace=False):
        self.loaded = shapes

    def setDirty(self):
        self.dirty = True

    def refresh_invalid_polygon_state(self):
        return [], []


def points(shape):
    return [(point.x(), point.y()) for point in shape.points]


def test_main_window_uses_copy_paste_mixin():
    from labelme.dlcv.app import MainWindow

    assert MainWindow.copySelectedShape is controller.CopyPasteMixin.copySelectedShape
    assert MainWindow.pasteSelectedShape is controller.CopyPasteMixin.pasteSelectedShape


def test_selected_polygon_uses_polygon_copy(monkeypatch):
    messages = []
    monkeypatch.setattr(controller, "notification", lambda *args: messages.append(args))
    window = Window([Shape([(10, 10), (20, 10), (20, 20)])])

    window.copySelectedShape()

    assert window._copied_shapes is not None
    assert window.actions.paste.enabled is True
    assert any("多边形已复制" in args for args in messages)


def test_visual_polygon_selection_is_copied_when_canvas_list_is_stale(monkeypatch):
    messages = []
    monkeypatch.setattr(controller, "notification", lambda *args: messages.append(args))
    shape = Shape([(10, 10), (20, 10), (20, 20)])
    window = Window([])
    window.canvas.shapes = [shape]

    window.copySelectedShape()

    assert window._copied_shapes is not None
    assert any("多边形已复制" in args for args in messages)


def test_invalid_copy_clears_previous_polygon(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    window = Window([Shape([(0, 0), (20, 20), (20, 0), (0, 20)])])
    window._copied_shapes = [Shape([(1, 1), (2, 1), (2, 2)])]
    window.actions.paste.enabled = True

    window.copySelectedShape()

    assert window._copied_shapes is None
    assert window.actions.paste.enabled is False


def test_no_selection_copies_image(monkeypatch):
    copied = []
    messages = []
    monkeypatch.setattr(controller, "copy_file_to_clipboard", copied.append)
    monkeypatch.setattr(controller, "notification", lambda *args: messages.append(args))
    window = Window([])

    window.copySelectedShape()

    assert copied == ["C:/data/a.png"]
    assert window._copied_shapes is None
    assert window.actions.paste.enabled is False
    assert any("图像已复制" in args for args in messages)


def test_same_image_paste_offsets_polygon(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    monkeypatch.setattr(controller, "STORE", SimpleNamespace(paste_follow_mouse=False))
    source = Shape([(10, 10), (20, 10), (20, 20)])
    window = Window([])
    window._copied_shapes = [source]
    window._copied_shapes_source = copy_paste.normalize_image_path(window.imagePath)

    window.pasteSelectedShape()

    assert points(window.loaded[0]) == [(20, 20), (30, 20), (30, 30)]
    assert window.dirty is True


def test_same_image_edge_paste_moves_away_from_original(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    monkeypatch.setattr(controller, "STORE", SimpleNamespace(paste_follow_mouse=False))
    source = Shape([(90.999, 70.999), (99.999, 70.999), (99.999, 79.999)])
    window = Window([])
    window._copied_shapes = [source]
    window._copied_shapes_source = copy_paste.normalize_image_path(window.imagePath)

    window.pasteSelectedShape()

    expected = [(80.999, 60.999), (89.999, 60.999), (89.999, 69.999)]
    for actual_point, expected_point in zip(points(window.loaded[0]), expected):
        assert actual_point == pytest.approx(expected_point)


def test_other_image_keeps_original_coordinates(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    monkeypatch.setattr(controller, "STORE", SimpleNamespace(paste_follow_mouse=False))
    source = Shape([(10, 10), (20, 10), (20, 20)])
    window = Window([])
    window.imagePath = "C:/data/b.png"
    window.filename = window.imagePath
    window._copied_shapes = [source]
    window._copied_shapes_source = copy_paste.normalize_image_path("C:/data/a.png")

    window.pasteSelectedShape()

    assert points(window.loaded[0]) == [(10, 10), (20, 10), (20, 20)]


def test_follow_cursor_places_group_top_left_at_cursor(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    monkeypatch.setattr(controller, "STORE", SimpleNamespace(paste_follow_mouse=True))
    source = Shape([(10, 10), (20, 10), (20, 20)])
    window = Window([])
    window._copied_shapes = [source]
    window._copied_shapes_source = copy_paste.normalize_image_path(window.imagePath)

    window.pasteSelectedShape()

    assert points(window.loaded[0]) == [(50, 40), (60, 40), (60, 50)]


def test_paste_moves_whole_polygon_inside_without_changing_shape(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    monkeypatch.setattr(controller, "STORE", SimpleNamespace(paste_follow_mouse=False))
    source = Shape([(95, 70), (99, 70), (99, 75)])
    window = Window([])
    window._copied_shapes = [source]
    window._copied_shapes_source = copy_paste.normalize_image_path("C:/data/b.png")

    window.pasteSelectedShape()

    assert points(window.loaded[0]) == [(95, 70), (99, 70), (99, 75)]
    original_edges = [(4, 0), (0, 5)]
    pasted = points(window.loaded[0])
    assert [
        (pasted[1][0] - pasted[0][0], pasted[1][1] - pasted[0][1]),
        (pasted[2][0] - pasted[1][0], pasted[2][1] - pasted[1][1]),
    ] == original_edges


def test_polygon_larger_than_image_is_rejected():
    shape = Shape([(0, 0), (120, 0), (120, 10)])
    with pytest.raises(copy_paste.CopyPasteError, match="too_large"):
        copy_paste.placement_translation(
            [shape],
            same_image=False,
            follow_cursor=False,
            cursor_xy=None,
            max_x=100,
            max_y=80,
            offset=0,
        )


def test_invalid_polygon_is_rejected():
    bowtie = Shape([(0, 0), (20, 20), (20, 0), (0, 20)])
    with pytest.raises(copy_paste.CopyPasteError, match="invalid"):
        copy_paste.validate_shape(bowtie)


def test_out_of_range_polygon_is_moved_inside_before_save(monkeypatch):
    monkeypatch.setattr(controller, "notification", lambda *_args: None)
    shape = Shape([(-5, 10), (5, 10), (5, 20)])
    window = Window([])
    window.canvas.shapes = [shape]

    assert window.prepare_polygons_for_save() is True
    assert points(shape) == [(0, 10), (10, 10), (10, 20)]


def test_invalid_polygon_blocks_save(monkeypatch):
    messages = []
    monkeypatch.setattr(controller, "notification", lambda *args: messages.append(args))
    shape = Shape([(0, 0), (20, 20), (20, 0), (0, 20)])
    window = Window([])
    window.canvas.shapes = [shape]

    assert window.prepare_polygons_for_save() is False
    assert window.selected == [shape]
    assert any("多边形非法，无法保存" in args for args in messages)

def test_help_menu_about_dialog_shows_runtime_version(monkeypatch):
    from labelme import __appname__, __version__
    from labelme.dlcv import app as app_module
    from qtpy import QtWidgets

    monkeypatch.setattr(app_module, "dlcv_tr", lambda text: text)
    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class AboutWindow(QtWidgets.QWidget):
        show_about_dialog = app_module.MainWindow.show_about_dialog

    window = AboutWindow()
    window.actions = SimpleNamespace()
    window.menus = SimpleNamespace(help=QtWidgets.QMenu(window))
    window.menus.help.addAction("使用文档")

    app_module.MainWindow._init_about_action(window)

    menu_actions = window.menus.help.actions()
    assert menu_actions[-2].isSeparator()
    assert menu_actions[-1] is window.actions.about
    assert window.actions.about.text() == "关于"

    window.actions.about.trigger()
    qt_app.processEvents()

    assert window._about_dialog.windowTitle() == "关于"
    version_label = window._about_dialog.findChild(QtWidgets.QLabel)
    assert version_label.text() == f"{__appname__}\n版本：{__version__}"
    window._about_dialog.close()
    window.close()
