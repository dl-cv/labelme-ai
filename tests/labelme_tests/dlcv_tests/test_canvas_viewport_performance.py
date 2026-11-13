"""Visible-region culling uses the same transform and extent as shape painting."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from labelme.dlcv import canvas as canvas_module
from labelme.dlcv import shape as shape_module
from labelme.dlcv.canvas import Canvas
from labelme.dlcv.shape import Shape


@pytest.fixture(scope="module")
def viewport_qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def viewport_canvas(viewport_qapp, monkeypatch):
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
    for name, rgba in (
        ("line_color", (0, 255, 0, 255)),
        ("fill_color", (0, 255, 0, 64)),
        ("select_line_color", (255, 255, 255, 255)),
        ("select_fill_color", (0, 255, 0, 128)),
        ("vertex_fill_color", (0, 255, 0, 255)),
        ("hvertex_fill_color", (255, 255, 255, 255)),
    ):
        monkeypatch.setattr(Shape, name, QtGui.QColor(*rgba))
    monkeypatch.setattr(Shape, "scale", 1.0)
    canvas = Canvas()
    canvas.resize(320, 240)
    pixmap = QtGui.QPixmap(2000, 1600)
    pixmap.fill(QtCore.Qt.white)
    canvas.loadPixmap(pixmap)
    yield canvas, settings
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()
    canvas.close()
    canvas.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def _box(x, y, label="part"):
    return Shape(label=label, shape_type="rotation", direction=0,
                 points=[[x, y], [x + 40, y], [x + 40, y + 30], [x, y + 30]])


def _render(canvas):
    image = QtGui.QImage(canvas.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.white)
    canvas.render(image)
    return image


@pytest.mark.parametrize("scale,offset,visible,hidden", [
    (1.0, (0, 0), (100, 100), (1200, 700)),
    (1.0, (-1000, -500), (1100, 600), (100, 100)),
    (0.25, (-1000, 0), (1200, 100), (100, 100)),
])
def test_culling_accounts_for_scale_pan_and_center(
    viewport_canvas, monkeypatch, scale, offset, visible, hidden
):
    canvas, _ = viewport_canvas
    canvas.scale = scale
    canvas.offset = QtCore.QPointF(*offset)
    near, far = _box(*visible), _box(*hidden)
    canvas.loadShapes([near, far])
    near_paint = Mock(wraps=near.paint)
    far_paint = Mock(wraps=far.paint)
    monkeypatch.setattr(near, "paint", near_paint)
    monkeypatch.setattr(far, "paint", far_paint)
    _render(canvas)
    near_paint.assert_called_once()
    far_paint.assert_not_called()


def test_full_image_fit_avoids_unnecessary_bounds_work(viewport_canvas, monkeypatch):
    canvas, _ = viewport_canvas
    canvas.scale = 0.1
    shape = _box(100, 100)
    canvas.loadShapes([shape])
    bounds = Mock(side_effect=AssertionError("full-image view does not need culling"))
    monkeypatch.setattr(shape, "paintBounds", bounds)
    _render(canvas)
    bounds.assert_not_called()


def test_empty_canvas_does_not_read_render_settings(viewport_canvas, monkeypatch):
    canvas, _ = viewport_canvas
    canvas.shapes = []
    monkeypatch.setattr(canvas_module, "STORE", SimpleNamespace(canvas_brush_enabled=True))
    _render(canvas)


@pytest.mark.parametrize("feature", ["label", "arrow", "vertex", "circle", "cross"])
def test_culling_preserves_pixels_from_geometry_outside_viewport(
    viewport_canvas, monkeypatch, feature
):
    canvas, settings = viewport_canvas
    if feature == "label":
        shape = _box(-130, 100, "very long annotation name reaching into view")
    elif feature == "arrow":
        shape = _box(-65, 100, label=None)
        # A long direction arrow can reach the viewport without its box doing so.
        shape.points = [QtCore.QPointF(-300, 80), QtCore.QPointF(-30, 80),
                        QtCore.QPointF(-30, 120), QtCore.QPointF(-300, 120)]
    elif feature == "vertex":
        shape = _box(-60, 100, label=None)
        shape.highlightVertex(1, Shape.NEAR_VERTEX)
    elif feature == "circle":
        shape = Shape(shape_type="circle", points=[[-40, 100], [-40, 20]])
    else:
        shape = _box(-90, 100, label=None)
        settings.canvas_display_shape_center_cross = True
        settings.canvas_shape_center_cross_length = 200
    canvas.loadShapes([shape])
    paint = Mock(wraps=shape.paint)
    monkeypatch.setattr(shape, "paint", paint)
    culled = _render(canvas)
    paint.assert_called_once()
    monkeypatch.setattr(shape, "paintBounds", lambda *args: QtCore.QRectF(-1e6, -1e6, 2e6, 2e6))
    assert culled == _render(canvas)


def test_culling_reads_mutated_geometry_and_visibility(viewport_canvas, monkeypatch):
    canvas, _ = viewport_canvas
    shape = _box(1500, 900)
    canvas.loadShapes([shape])
    paint = Mock(wraps=shape.paint)
    monkeypatch.setattr(shape, "paint", paint)
    _render(canvas)
    paint.assert_not_called()
    # Direct QPointF mutations are used by existing fix/rotate/edit operations.
    for point in shape.points:
        point.setX(point.x() - 1400)
        point.setY(point.y() - 800)
    _render(canvas)
    paint.assert_called_once()
    canvas.setShapeVisible(shape, False)
    paint.reset_mock()
    _render(canvas)
    paint.assert_not_called()


def test_scroll_area_uses_viewport_not_full_canvas(viewport_canvas, viewport_qapp, monkeypatch):
    canvas, _ = viewport_canvas
    near, far = _box(1100, 600), _box(100, 100)
    canvas.loadShapes([near, far])
    area = QtWidgets.QScrollArea()
    area.resize(340, 260)
    area.setWidget(canvas)
    canvas.resize(2000, 1600)
    area.show()
    area.horizontalScrollBar().setValue(1000)
    area.verticalScrollBar().setValue(500)
    viewport_qapp.processEvents()
    near_paint = Mock(wraps=near.paint)
    far_paint = Mock(wraps=far.paint)
    monkeypatch.setattr(near, "paint", near_paint)
    monkeypatch.setattr(far, "paint", far_paint)
    _render(canvas)
    near_paint.assert_called_once()
    far_paint.assert_not_called()
    area.takeWidget()
    area.close()
    area.deleteLater()


@pytest.mark.parametrize("hide_background", [False, True])
def test_zoom_preview_keeps_selected_hover_and_hidden_shape_rules(
    viewport_canvas, monkeypatch, hide_background
):
    canvas, _ = viewport_canvas
    ordinary, selected, hovered, hidden = [_box(40 + i * 50, 100) for i in range(4)]
    canvas.loadShapes([ordinary, selected, hovered, hidden])
    selected.selected = True
    canvas.hShape = hovered
    canvas._hideBackround = hide_background
    canvas.setShapeVisible(hidden, False)
    canvas._zoom_preview_active = True
    calls = []
    preview = Mock(side_effect=lambda painter, shapes, *args: calls.extend(shapes))
    monkeypatch.setattr(canvas_module, "paint_zoom_preview", preview)
    paints = [Mock(wraps=shape.paint) for shape in canvas.shapes]
    for shape, paint in zip(canvas.shapes, paints):
        monkeypatch.setattr(shape, "paint", paint)
    _render(canvas)
    assert calls == ([] if hide_background else [ordinary])
    paints[0].assert_not_called()
    paints[1].assert_called_once()
    if hide_background:
        paints[2].assert_not_called()
    else:
        paints[2].assert_called_once()
    paints[3].assert_not_called()


def test_rotation_hover_does_not_search_non_insertable_edges(viewport_canvas, monkeypatch):
    canvas, _ = viewport_canvas
    shape = _box(100, 100)
    canvas.loadShapes([shape])
    nearest_edge = Mock(wraps=shape.nearestEdge)
    monkeypatch.setattr(shape, "nearestEdge", nearest_edge)
    event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(120, 115),
                             QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
    canvas.mouseMoveEvent(event)
    nearest_edge.assert_not_called()
    assert canvas.hShape is shape
