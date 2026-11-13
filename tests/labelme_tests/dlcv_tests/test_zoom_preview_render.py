"""Offscreen checks for the temporary batched dense-scene zoom outlines."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from qtpy import QtCore, QtGui, QtWidgets

from labelme.dlcv.shape import Shape
from labelme.dlcv.shape_render import ShapeRenderSettings
from labelme.dlcv.zoom_preview import paint_zoom_preview


@pytest.fixture(scope="module", autouse=True)
def preview_application():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def preview_colors(monkeypatch):
    for name, rgba in {
        "line_color": (0, 255, 0, 255),
        "fill_color": (0, 255, 0, 64),
        "select_line_color": (255, 255, 255, 255),
        "select_fill_color": (0, 255, 0, 128),
        "vertex_fill_color": (0, 255, 0, 255),
        "hvertex_fill_color": (255, 255, 255, 255),
    }.items():
        monkeypatch.setattr(Shape, name, QtGui.QColor(*rgba))
    monkeypatch.setattr(Shape, "scale", 1)


class RecordingPainter(QtGui.QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.draws = []
        self.texts = 0

    def drawPath(self, path):
        self.draws.append((QtGui.QPen(self.pen()), QtGui.QPainterPath(path)))
        return super().drawPath(path)

    def drawText(self, *args):
        self.texts += 1
        return super().drawText(*args)


def image():
    result = QtGui.QImage(400, 300, QtGui.QImage.Format_ARGB32_Premultiplied)
    result.fill(0)
    return result


def pixels(result):
    buffer = result.bits()
    buffer.setsize(result.byteCount())
    return np.frombuffer(buffer, dtype=np.uint8).reshape(
        result.height(), result.bytesPerLine() // 4, 4,
    ).copy()


def settings(painter, scale=1):
    store = SimpleNamespace(
        canvas_display_shape_label=True, canvas_shape_label_font_size=12,
        canvas_shape_label_position="center", canvas_display_rotation_arrow=True,
        canvas_points_to_crosshair=False, canvas_display_shape_center_cross=True,
        canvas_shape_center_cross_length=100, canvas_highlight_start_point=True,
    )
    return ShapeRenderSettings.from_store(scale, painter, store)


def make_shape(kind="rotation", points=None, **kwargs):
    if points is None:
        points = [(80, 80), (120, 80), (120, 120), (80, 120)]
    return Shape(shape_type=kind, points=[list(point) for point in points],
                 label="component very long label", **kwargs)


def test_same_style_is_batched_and_decorations_are_not_drawn():
    result = image()
    painter = RecordingPainter(result)
    shapes = [make_shape() for _ in range(20)]
    originals = [(tuple((p.x(), p.y()) for p in shape.points), shape.fill,
                  shape.direction, shape.arrow_center, shape.arrow_end) for shape in shapes]
    for shape in shapes:
        shape.paint = Mock(side_effect=AssertionError("outline must not call paint"))
        shape.paintBounds = Mock(side_effect=AssertionError("do not compute detailed bounds"))
    try:
        paint_zoom_preview(painter, shapes, 1, QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert len(painter.draws) == 1
        assert painter.draws[0][1].elementCount() == 20 * 5
        assert painter.texts == 0
    finally:
        painter.end()
    assert originals == [(tuple((p.x(), p.y()) for p in shape.points), shape.fill,
                           shape.direction, shape.arrow_center, shape.arrow_end) for shape in shapes]
    alpha = pixels(result)[:, :, 3]
    assert alpha[80, 100] > 0
    assert alpha[100, 100] == 0  # no fill, label, center cross, or vertex handles


@pytest.mark.parametrize("kind,points,elements", [
    ("polygon", [(20, 20), (80, 20), (50, 80)], 4),
    ("rotation", [(20, 20), (80, 20), (80, 80), (20, 80)], 5),
    ("rectangle", [(80, 80), (20, 20)], 5),
    ("circle", [(80, 80), (100, 100)], 13),
    ("line", [(20, 20), (80, 80)], 2),
    ("linestrip", [(20, 20), (80, 20), (80, 80)], 3),
    ("point", [(80, 80)], 4),
    ("points", [(80, 80), (100, 100)], 8),
])
def test_supported_geometry_outlines(kind, points, elements):
    shape = make_shape(kind, points)
    result = image()
    painter = RecordingPainter(result)
    try:
        paint_zoom_preview(painter, [shape], 1, QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert len(painter.draws) == 1
        assert painter.draws[0][1].elementCount() == elements
    finally:
        painter.end()
    assert pixels(result)[:, :, 3].any()


@pytest.mark.parametrize("scale", [0.1, 1, 2])
def test_culling_uses_scaled_geometry_and_not_label_or_arrow_extents(scale):
    # The label would cross into the viewport, but labels are absent in preview.
    far = make_shape(points=[(-1000, 0), (-990, 0), (-990, 10), (-1000, 10)])
    near = make_shape(points=[(10, 10), (20, 10), (20, 20), (10, 20)])
    result = image()
    painter = RecordingPainter(result)
    try:
        paint_zoom_preview(painter, [far, near], scale,
                           QtCore.QRectF(0, 0, 400, 300), settings(painter, scale))
        assert len(painter.draws) == 1
        assert painter.draws[0][1].elementCount() == 5
        assert painter.draws[0][1].boundingRect().contains(QtCore.QPointF(10, 10))
    finally:
        painter.end()


def test_circle_true_radius_and_pen_padding_prevent_false_culling():
    circle = make_shape("circle", [(450, 150), (500, 200)])
    line = make_shape("line", [(-2, 30), (-2, 70)])
    line.PEN_WIDTH = 6
    result = image()
    painter = RecordingPainter(result)
    try:
        paint_zoom_preview(painter, [circle, line], 1,
                           QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert len(painter.draws) == 2
    finally:
        painter.end()
    alpha = pixels(result)[:, :, 3]
    assert alpha[:, -1].any()  # circle extends left into viewport
    assert alpha[:, 0].any()  # thick pen crosses the left boundary


def test_rgba_and_width_use_normal_qpen_semantics():
    shapes = [make_shape() for _ in range(3)]
    shapes[1].line_color = QtGui.QColor(0, 255, 0, 120)
    shapes[2].PEN_WIDTH = 5
    result = image()
    painter = RecordingPainter(result)
    try:
        paint_zoom_preview(painter, shapes, 1,
                           QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert len(painter.draws) == 3
        assert painter.draws[1][0].color().alpha() == 120
        assert painter.draws[2][0].width() == 5
    finally:
        painter.end()


def test_none_color_matches_original_qpen_exception_and_restores_state():
    shape = make_shape()
    shape.line_color = None
    result = image()
    painter = RecordingPainter(result)
    painter.translate(5, 7)
    old_transform, old_pen = painter.worldTransform(), painter.pen()
    try:
        with pytest.raises(TypeError):
            QtGui.QPen(None)
        with pytest.raises(TypeError):
            paint_zoom_preview(painter, [shape], 1,
                               QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert painter.worldTransform() == old_transform
        assert painter.pen() == old_pen
    finally:
        painter.end()


@pytest.mark.parametrize("color", [QtCore.Qt.red, QtCore.Qt.DashLine])
def test_non_qcolor_inputs_preserve_qpen_constructor_styles(color):
    shape = make_shape()
    shape.line_color = color
    result = image()
    painter = RecordingPainter(result)
    try:
        expected = QtGui.QPen(color)
        expected.setWidth(shape.PEN_WIDTH)
        paint_zoom_preview(painter, [shape], 1,
                           QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert painter.draws[0][0] == expected
    finally:
        painter.end()


@pytest.mark.parametrize("scale", [0.125, 0.5, 2])
@pytest.mark.parametrize("device_ratio", [1, 2])
def test_logical_stroke_width_matches_direct_pixel_geometry(scale, device_ratio):
    shape = make_shape(points=[(20, 20), (60, 20), (60, 60), (20, 60)])
    reference, preview = image(), image()
    for result, is_preview in ((reference, False), (preview, True)):
        result.setDevicePixelRatio(device_ratio)
        painter = QtGui.QPainter(result)
        try:
            if is_preview:
                paint_zoom_preview(painter, [shape], scale,
                                   QtCore.QRectF(0, 0, 400, 300), settings(painter, scale))
            else:
                pen = QtGui.QPen(shape.line_color)
                pen.setWidth(shape.PEN_WIDTH)
                painter.setPen(pen)
                path = QtGui.QPainterPath()
                for i, point in enumerate([*shape.points, shape.points[0]]):
                    target = QtCore.QPointF(point.x() * scale, point.y() * scale)
                    if i:
                        path.lineTo(target)
                    else:
                        path.moveTo(target)
                painter.drawPath(path)
        finally:
            painter.end()
    np.testing.assert_array_equal(pixels(reference), pixels(preview))


def test_preserves_painter_state_and_applies_existing_translation():
    result = image()
    painter = RecordingPainter(result)
    painter.setBrush(QtGui.QColor("red"))
    painter.setPen(QtGui.QPen(QtGui.QColor("blue"), 7))
    painter.translate(-500, -300)
    old_pen, old_brush, old_transform = painter.pen(), painter.brush(), painter.worldTransform()
    try:
        shape = make_shape(points=[(550, 350), (590, 350), (590, 390), (550, 390)])
        paint_zoom_preview(painter, [shape], 1,
                           QtCore.QRectF(500, 300, 400, 300), settings(painter))
        assert painter.pen() == old_pen
        assert painter.brush() == old_brush
        assert painter.worldTransform() == old_transform
    finally:
        painter.end()
    alpha = pixels(result)[:, :, 3]
    assert alpha[50, 70] > 0
    assert alpha[70, 70] == 0


def test_mask_fallback_matches_exact_paint_and_keeps_geometry():
    mask = make_shape("mask", [(80, 80), (100, 100)],
                      mask=np.ones((20, 20), dtype=bool))
    reference, preview = image(), image()
    original = tuple((point.x(), point.y()) for point in mask.points)
    for result, is_preview in ((reference, False), (preview, True)):
        painter = QtGui.QPainter(result)
        try:
            frame = settings(painter)
            if is_preview:
                paint_zoom_preview(painter, [mask], 1, QtCore.QRectF(0, 0, 400, 300), frame)
            else:
                mask.paint(painter, frame)
        finally:
            painter.end()
    np.testing.assert_array_equal(pixels(reference), pixels(preview))
    assert original == tuple((point.x(), point.y()) for point in mask.points)


def test_unknown_fallback_flushes_groups_and_restores_state():
    first, last = make_shape(), make_shape()
    unknown = SimpleNamespace(shape_type="custom", mask=None)
    result = image()
    painter = RecordingPainter(result)
    calls = []

    def fallback(active_painter, frame):
        calls.append(len(active_painter.draws))
        active_painter.translate(10000, 10000)

    unknown.paint = Mock(side_effect=fallback)
    frame = settings(painter)
    try:
        paint_zoom_preview(painter, [first, unknown, last], 1,
                           QtCore.QRectF(0, 0, 400, 300), frame)
        unknown.paint.assert_called_once_with(painter, frame)
        assert calls == [1]
        assert len(painter.draws) == 2
        assert painter.worldTransform().isIdentity()
    finally:
        painter.end()


def test_direct_point_mutation_has_no_stale_preview_geometry():
    shape = make_shape()
    result = image()
    painter = RecordingPainter(result)
    try:
        frame = settings(painter)
        paint_zoom_preview(painter, [shape], 1, QtCore.QRectF(0, 0, 400, 300), frame)
        assert len(painter.draws) == 1
        for point in shape.points:
            point.setX(point.x() + 5000)
        paint_zoom_preview(painter, [shape], 1, QtCore.QRectF(0, 0, 400, 300), frame)
        assert len(painter.draws) == 1
    finally:
        painter.end()


@pytest.mark.parametrize("kind,points", [
    ("polygon", []), ("rotation", [(0, 0)]),
    ("rectangle", [(0, 0)]), ("circle", [(0, 0)]),
])
def test_empty_or_incomplete_geometries_do_not_raise(kind, points):
    result = image()
    painter = RecordingPainter(result)
    try:
        paint_zoom_preview(painter, [make_shape(kind, points)], 1,
                           QtCore.QRectF(0, 0, 400, 300), settings(painter))
        assert not painter.draws
    finally:
        painter.end()
