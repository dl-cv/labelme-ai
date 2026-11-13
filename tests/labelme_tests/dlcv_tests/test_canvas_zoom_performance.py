"""Dense-wheel previews preserve annotation data and settle back to full detail."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from labelme.dlcv import canvas as canvas_module
from labelme.dlcv import shape as shape_module
from labelme.dlcv.canvas import Canvas
from labelme.dlcv.shape import Shape


@pytest.fixture
def zoom_settings(monkeypatch):
    settings = SimpleNamespace(
        canvas_brush_enabled=True,
        canvas_display_shape_label=True,
        canvas_shape_label_font_size=10,
        canvas_shape_label_position="center",
        canvas_display_rotation_arrow=True,
        canvas_points_to_crosshair=False,
        canvas_display_shape_center_cross=False,
        canvas_shape_center_cross_length=10,
        canvas_highlight_start_point=False,
    )
    monkeypatch.setattr(canvas_module, "STORE", settings)
    monkeypatch.setattr(shape_module, "STORE", settings)
    monkeypatch.setattr(Shape, "scale", 1.0)
    for name, rgba in (
        ("line_color", (0, 255, 0, 255)),
        ("fill_color", (0, 255, 0, 64)),
        ("select_line_color", (255, 255, 255, 255)),
        ("select_fill_color", (0, 255, 0, 128)),
        ("vertex_fill_color", (0, 255, 0, 255)),
        ("hvertex_fill_color", (255, 255, 255, 255)),
    ):
        monkeypatch.setattr(Shape, name, QtGui.QColor(*rgba))
    return settings


@pytest.fixture
def zoom_canvas(qtbot, zoom_settings):
    canvas = Canvas()
    qtbot.addWidget(canvas)
    canvas.resize(320, 240)
    pixmap = QtGui.QPixmap(400, 300)
    pixmap.fill(QtCore.Qt.white)
    canvas.loadPixmap(pixmap)
    yield canvas
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()


def _populate(canvas, count):
    shapes = []
    for index in range(count):
        x, y = 10 + index % 40 * 7, 10 + index // 40 * 7
        shapes.append(Shape(
            label="part", shape_type="rotation", direction=0.0,
            points=[[x, y], [x + 5, y], [x + 5, y + 4], [x, y + 4]],
        ))
    canvas.loadShapes(shapes)
    return shapes


def _wheel(canvas, delta=120, position=(120, 90), horizontal=0):
    event = QtGui.QWheelEvent(
        QtCore.QPointF(*position), QtCore.QPointF(*position),
        QtCore.QPoint(), QtCore.QPoint(horizontal, delta),
        QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
        QtCore.Qt.NoScrollPhase, False,
    )
    canvas.wheelEvent(event)
    return event


def _active(canvas):
    return getattr(canvas, "_zoom_preview_active", False)


def _geometry(canvas):
    return tuple(
        (tuple((point.x(), point.y()) for point in shape.points), shape.direction)
        for shape in canvas.shapes
    )


def _render(canvas):
    image = QtGui.QImage(canvas.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.white)
    canvas.render(image)
    return image


@pytest.mark.parametrize("count", [999, 1000])
@pytest.mark.parametrize("delta", [120, -120])
def test_dense_preview_starts_before_zoom_request(zoom_canvas, count, delta):
    canvas = zoom_canvas
    _populate(canvas, count)
    observed = []
    canvas.zoomRequest.connect(
        lambda amount, point: observed.append((amount, point, _active(canvas)))
    )
    event = _wheel(canvas, delta)

    assert observed == [(delta, QtCore.QPoint(120, 90), count >= 1000)]
    assert _active(canvas) is (count >= 1000)
    assert event.isAccepted()


@pytest.mark.parametrize("horizontal", [0, 120])
def test_zero_vertical_delta_does_not_zoom_or_start_preview(zoom_canvas, horizontal):
    canvas = zoom_canvas
    _populate(canvas, 1000)
    zoom = Mock()
    canvas.zoomRequest.connect(zoom)
    _wheel(canvas, 0, horizontal=horizontal)
    zoom.assert_not_called()
    assert not _active(canvas)


def test_continuous_wheels_restart_settling_timer(zoom_canvas, qtbot):
    canvas = zoom_canvas
    _populate(canvas, 1000)
    assert canvas._zoom_preview_timer.isSingleShot()
    assert canvas._zoom_preview_timer.interval() == 250
    _wheel(canvas)
    assert _active(canvas)
    qtbot.wait(150)
    assert _active(canvas)
    _wheel(canvas, -120)
    qtbot.wait(150)
    # More than 250 ms after the first wheel, but less than 250 after the last.
    assert _active(canvas)
    qtbot.waitUntil(lambda: not _active(canvas), timeout=1000)


def test_preview_render_bypasses_normal_paint_then_restores_exact_image(
    zoom_canvas, qtbot, monkeypatch
):
    canvas = zoom_canvas
    _populate(canvas, 1000)
    full = _render(canvas)
    normal_paint = Mock(wraps=Shape.paint)
    # Keep descriptor binding while recording real Shape.paint calls.
    def recorded_paint(shape, *args, **kwargs):
        return normal_paint(shape, *args, **kwargs)
    monkeypatch.setattr(Shape, "paint", recorded_paint)
    _wheel(canvas)
    assert _active(canvas)
    preview = _render(canvas)
    normal_paint.assert_not_called()
    assert preview != full

    updates = Mock(wraps=canvas.update)
    monkeypatch.setattr(canvas, "update", updates)
    qtbot.waitUntil(lambda: not _active(canvas), timeout=1000)
    assert updates.called
    assert _render(canvas) == full
    assert normal_paint.call_count == 1000


def test_sparse_wheel_keeps_normal_render_path(zoom_canvas, monkeypatch):
    canvas = zoom_canvas
    shapes = _populate(canvas, 999)
    paint = Mock(wraps=shapes[0].paint)
    monkeypatch.setattr(shapes[0], "paint", paint)
    _wheel(canvas)
    _render(canvas)
    assert not _active(canvas)
    paint.assert_called_once()


def test_wheel_preview_does_not_modify_shapes_undo_or_emit_save(
    zoom_canvas, qtbot, monkeypatch
):
    canvas = zoom_canvas
    _populate(canvas, 1000)
    geometry = _geometry(canvas)
    backups = tuple(canvas.shapesBackups)
    store = Mock(wraps=canvas.storeShapes)
    monkeypatch.setattr(canvas, "storeShapes", store)
    moved = Mock()
    canvas.shapeMoved.connect(moved)
    for delta in (120, 120, -120):
        _wheel(canvas, delta)
        assert _active(canvas)
        assert _geometry(canvas) == geometry
    _render(canvas)
    qtbot.waitUntil(lambda: not _active(canvas), timeout=1000)
    _render(canvas)
    assert _geometry(canvas) == geometry
    assert tuple(canvas.shapesBackups) == backups
    store.assert_not_called()
    moved.assert_not_called()


@pytest.mark.parametrize("operation", [
    "reset", "load_shapes", "load_pixmap", "replace_pixmap", "mouse_press", "key_press",
    "focus_out",
])
def test_loading_resetting_or_new_edit_ends_preview(zoom_canvas, operation):
    canvas = zoom_canvas
    _populate(canvas, 1000)
    _wheel(canvas)
    assert _active(canvas)
    if operation == "reset":
        canvas.resetState()
    elif operation == "load_shapes":
        canvas.loadShapes([])
    elif operation in ("load_pixmap", "replace_pixmap"):
        pixmap = QtGui.QPixmap(400, 300)
        pixmap.fill(QtCore.Qt.white)
        canvas.loadPixmap(pixmap, clear_shapes=operation == "load_pixmap")
    elif operation == "mouse_press":
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress, QtCore.QPointF(300, 220),
            QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
        )
        canvas.mousePressEvent(event)
    elif operation == "key_press":
        event = QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier,
        )
        canvas.keyPressEvent(event)
    else:
        canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert not _active(canvas)


@pytest.fixture
def zoom_window(qtbot, monkeypatch, tmp_path, zoom_settings):
    # DLCV MainWindow inherits these real zoom/anchor/limit methods unchanged.
    # Use its base window so this test does not require dlcv_core.image_json.
    from labelme import app as app_module
    from labelme.config import get_config

    monkeypatch.setattr(app_module, "Canvas", Canvas)
    image_path = tmp_path / "zoom-anchor.png"
    image = QtGui.QImage(640, 480, QtGui.QImage.Format_RGB32)
    image.fill(QtCore.Qt.white)
    assert image.save(str(image_path))
    config = get_config()
    config["auto_save"] = False
    config["keep_prev"] = False
    def fail_message(self, title, message):
        raise AssertionError(f"Unexpected window error: {title}: {message}")

    monkeypatch.setattr(app_module.MainWindow, "errorMessage", fail_message)
    # No queued loadFile: full-suite DLCV imports can replace the base LabelFile.
    # Inject only the background; all wheel/zoom/layout arithmetic remains real.
    window = app_module.MainWindow(config=config, filename=None)
    window.imageList = []
    window.image = image
    window.imagePath = str(image_path)
    window.filename = str(image_path)
    window.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
    window.canvas.setEnabled(True)
    window.toggleActions(True)
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    window.setZoom(150)
    QtWidgets.QApplication.processEvents()
    yield window
    window.setClean()
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()


@pytest.mark.parametrize("count", [999, 1000])
@pytest.mark.parametrize("delta", [120, -120])
@pytest.mark.parametrize("start_view", ["fit", "magnified"])
def test_real_main_window_wheel_keeps_mouse_anchor(
    zoom_window, count, delta, start_view
):
    window = zoom_window
    canvas = window.canvas
    if start_view == "fit":
        window.adjustScale(initial=True)
        QtWidgets.QApplication.processEvents()
    _populate(canvas, count)
    viewport = window.centralWidget().viewport()
    anchor = QtCore.QPoint(viewport.width() // 3, viewport.height() // 3)
    position = anchor + QtCore.QPoint(
        window.scrollBars[QtCore.Qt.Horizontal].value(),
        window.scrollBars[QtCore.Qt.Vertical].value(),
    )
    before = canvas.transformPos(QtCore.QPointF(position))
    old_scale = canvas.scale
    _wheel(canvas, delta, (position.x(), position.y()))
    after_position = anchor + QtCore.QPoint(
        window.scrollBars[QtCore.Qt.Horizontal].value(),
        window.scrollBars[QtCore.Qt.Vertical].value(),
    )
    after = canvas.transformPos(QtCore.QPointF(after_position))

    assert after.x() == pytest.approx(before.x(), abs=1e-7)
    assert after.y() == pytest.approx(before.y(), abs=1e-7)
    assert canvas.scale > old_scale if delta > 0 else canvas.scale < old_scale
    assert _active(canvas) is (count >= 1000)


def test_real_main_window_wheel_respects_zoom_limits(zoom_window):
    window = zoom_window
    canvas = window.canvas
    _populate(canvas, 1000)
    minimum = window.minimumZoomValue()
    window.setZoom(minimum)
    _wheel(canvas, -120)
    assert window.zoomWidget.value() == minimum
    assert canvas.scale == pytest.approx(minimum / 100.0)

    maximum = window.zoomWidget.maximum()
    window.setZoom(maximum)
    _wheel(canvas, 120)
    assert window.zoomWidget.value() == maximum
    assert canvas.scale == pytest.approx(maximum / 100.0)
