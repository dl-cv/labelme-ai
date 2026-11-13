"""Offscreen regressions for frame snapshots and conservative paint culling."""

from collections import Counter
from dataclasses import replace

import numpy as np
import pytest
from qtpy import QtCore, QtGui, QtWidgets

from labelme.dlcv import shape as shape_module
from labelme.dlcv import shape_render
from labelme.dlcv.shape import Shape
from labelme.dlcv.shape_render import ShapeRenderSettings


class CountingStore:
    def __init__(self, **overrides):
        self.values = {
            "canvas_display_shape_label": True,
            "canvas_shape_label_font_size": 12,
            "canvas_shape_label_position": "center",
            "canvas_display_rotation_arrow": True,
            "canvas_points_to_crosshair": False,
            "canvas_display_shape_center_cross": True,
            "canvas_shape_center_cross_length": 100,
            "canvas_highlight_start_point": False,
        }
        self.values.update(overrides)
        self.reads = Counter()

    def __getattr__(self, name):
        if name in self.values:
            self.reads[name] += 1
            return self.values[name]
        raise AttributeError(name)


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def colors(monkeypatch):
    for attr, color in {
        "line_color": (0, 255, 0, 255),
        "fill_color": (0, 255, 0, 64),
        "select_line_color": (255, 255, 255, 255),
        "select_fill_color": (0, 255, 0, 128),
        "vertex_fill_color": (0, 255, 0, 255),
        "hvertex_fill_color": (255, 255, 255, 255),
    }.items():
        monkeypatch.setattr(Shape, attr, QtGui.QColor(*color))


def make_shape(kind="rotation", points=None, label="", **kwargs):
    if points is None:
        points = [(150, 150), (175, 150), (175, 175), (150, 175)]
    return Shape(shape_type=kind, points=[list(point) for point in points],
                 label=label, **kwargs)


def image():
    result = QtGui.QImage(800, 500, QtGui.QImage.Format_ARGB32_Premultiplied)
    result.fill(0)
    return result


def pixels(result):
    data = result.bits()
    data.setsize(result.byteCount())
    return np.frombuffer(data, dtype=np.uint8).reshape(
        result.height(), result.bytesPerLine() // 4, 4,
    ).copy()


def test_settings_read_once_for_multiple_shapes(monkeypatch):
    store = CountingStore()
    monkeypatch.setattr(shape_module, "STORE", store)
    monkeypatch.setattr(shape_render, "STORE", store)
    result = image()
    painter = QtGui.QPainter(result)
    try:
        settings = ShapeRenderSettings.from_store(1, painter)
        expected = Counter({name: 1 for name in store.values})
        assert store.reads == expected
        for _ in range(4):
            shape = make_shape(label="component")
            shape.paintBounds(1, settings)
            shape.paint(painter, settings)
        assert store.reads == expected
    finally:
        painter.end()


def test_rotation_label_is_drawn_once_and_font_restored(monkeypatch):
    class CountingPainter(QtGui.QPainter):
        def drawText(self, *args):
            self.text_draws += 1
            return super().drawText(*args)

    store = CountingStore()
    monkeypatch.setattr(shape_module, "STORE", store)
    result = image()
    painter = CountingPainter(result)
    painter.text_draws = 0
    font = QtGui.QFont("Arial", 9)
    painter.setFont(font)
    original_font = painter.font()
    try:
        shape = make_shape(label="component")
        shape.paint(painter)  # Existing callers need not supply settings.
        assert painter.text_draws == 1
        assert painter.font() == original_font
    finally:
        painter.end()


@pytest.mark.parametrize("scale", [0.15, 1, 2])
@pytest.mark.parametrize("position", ["center", "top_left", "bottom_right"])
@pytest.mark.parametrize("kind", ["rotation", "circle", "point", "polygon", "mask"])
def test_bounds_contain_rendered_pixels(scale, position, kind, monkeypatch):
    store = CountingStore(canvas_shape_label_position=position)
    points = {
        "circle": [(150, 150), (170, 170)],
        "point": [(150, 150)],
        "polygon": [(100, 100), (180, 100), (180, 180), (140, 120), (100, 180)],
        "mask": [(150, 150), (160, 160)],
    }.get(kind)
    shape = make_shape(kind, points=points, label="component_very_long_label_" * 3,
                       mask=np.ones((20, 30), dtype=bool) if kind == "mask" else None,
                       direction=225)
    shape.highlightVertex(0, shape.NEAR_VERTEX)
    monkeypatch.setattr(Shape, "scale", scale)
    result = image()
    # Device-specific DPI must be reflected in both label bounds and painting.
    result.setDotsPerMeterX(5000)
    result.setDotsPerMeterY(5000)
    painter = QtGui.QPainter(result)
    try:
        settings = ShapeRenderSettings.from_store(scale, painter, store)
        bounds = shape.paintBounds(scale, settings)
        shape.paint(painter, settings)
    finally:
        painter.end()
    alpha = pixels(result)[:, :, 3]
    ys, xs = np.nonzero(alpha)
    assert len(xs), kind
    actual = QtCore.QRectF(float(xs.min()), float(ys.min()),
                          float(xs.max() - xs.min() + 1),
                          float(ys.max() - ys.min() + 1))
    assert bounds.contains(actual), (kind, scale, position, bounds, actual)


@pytest.mark.parametrize("scale", [0.2, 1, 2])
@pytest.mark.parametrize("position", ["center", "top_left", "bottom_right"])
def test_viewport_culling_matches_full_render(scale, position, monkeypatch):
    monkeypatch.setattr(Shape, "scale", scale)
    shapes = [
        make_shape(label="long text across viewport boundary " * 5),
        make_shape("circle", [(300, 250), (370, 320)], label="circle"),
        make_shape("point", [(400, 220)], label="point"),
        make_shape(points=[(900, 80), (940, 80), (940, 120), (900, 120)],
                   direction=180, label="offscreen_label"),
        make_shape(points=[(10000, 10000), (10020, 10000),
                           (10020, 10020), (10000, 10020)], label="far away"),
    ]
    shapes[2].highlightVertex(0, shapes[2].NEAR_VERTEX)
    store = CountingStore(canvas_shape_label_position=position)
    viewport = QtCore.QRectF(100, 50, 800, 500)
    results = []
    skipped = 0
    for cull in (False, True):
        result = image()
        painter = QtGui.QPainter(result)
        painter.translate(-viewport.left(), -viewport.top())
        try:
            settings = ShapeRenderSettings.from_store(scale, painter, store)
            for shape in shapes:
                if cull and not shape.paintBounds(scale, settings).intersects(viewport):
                    skipped += 1
                    continue
                shape.paint(painter, settings)
        finally:
            painter.end()
        results.append(pixels(result))
    assert skipped
    np.testing.assert_array_equal(*results)


def test_bounds_follow_direct_point_mutation_and_direction(monkeypatch):
    monkeypatch.setattr(Shape, "scale", 3)
    store = CountingStore(canvas_display_shape_label=False,
                          canvas_display_shape_center_cross=False)
    settings = ShapeRenderSettings.from_store(3, store=store)
    shape = make_shape(points=[(0, 0), (1, 0), (1, 1), (0, 1)], direction=0)
    original = shape.paintBounds(3, settings)
    assert original.right() >= 37.5  # min 12 ORIGINAL-image px arrow, scaled by 3.
    shape.direction = 180
    rotated = shape.paintBounds(3, settings)
    for point in shape._rotation_arrow_points():
        assert rotated.contains(QtCore.QPointF(point.x() * 3, point.y() * 3))
    for point in shape.points:
        point.setX(point.x() + 1000)
    changed = shape.paintBounds(3, settings)
    assert changed.left() > original.right()
    shape.points = [QtCore.QPointF(5, 5)]
    shape.shape_type = "point"
    assert shape.paintBounds(3, settings).contains(QtCore.QPointF(15, 15))


def test_repeated_label_sizes_are_cached_only_within_frame():
    class CountingMetrics:
        def __init__(self):
            self.width_calls = 0

        def horizontalAdvance(self, text):
            self.width_calls += 1
            return len(text) * 8

        def height(self):
            return 15

    settings = ShapeRenderSettings.from_store(1, store=CountingStore())
    metrics = CountingMetrics()
    settings = replace(settings, label_font_metrics=metrics)
    for _ in range(3):
        for label in ("pad", "component", "pin", "text", "logo", "noumenon"):
            shape = make_shape(label=label)
            shape.paintBounds(1, settings)
            shape._label_paint_rect(1, settings)
    assert metrics.width_calls == 6
    shape._label_paint_rect(1, settings, metrics)
    assert metrics.width_calls == 7  # An explicit metrics override bypasses the cache.
    next_frame = replace(settings, label_sizes={})
    shape.paintBounds(1, next_frame)
    assert metrics.width_calls == 8


@pytest.mark.parametrize("scale", [0.01, 0.2, 1, 4])
@pytest.mark.parametrize("direction", [0, 37, 90, 179, 225, 315])
def test_cheap_arrow_bounds_contain_exact_arrow_points(scale, direction):
    settings = ShapeRenderSettings.from_store(scale, store=CountingStore(
        canvas_display_shape_label=False, canvas_display_shape_center_cross=False))
    for points in (
        [(0, 0), (1, 0), (1, 1), (0, 1)],
        [(0, 0), (900, 5), (901, 6), (1, 1)],
    ):
        shape = make_shape(points=points, direction=direction)
        bounds = shape.paintBounds(scale, settings)
        for point in shape._rotation_arrow_points():
            assert bounds.contains(QtCore.QPointF(point.x() * scale, point.y() * scale))


def test_arrow_cache_and_hit_test_follow_edits_without_repainting(monkeypatch):
    monkeypatch.setattr(shape_module, "STORE", CountingStore())
    shape = make_shape(points=[(100, 100), (200, 100), (200, 160), (100, 160)])
    original = shape._rotation_arrow_points()
    assert shape._rotation_arrow_points() is original
    original_mid = (original[0] + original[1]) / 2
    assert shape.isArrowHit(original_mid)
    # A culled shape may change without paint refreshing arrow_center/arrow_end.
    for point in shape.points:
        point.setX(point.x() + 1000)
    moved = shape._rotation_arrow_points()
    assert moved is not original
    assert not shape.isArrowHit(original_mid)
    assert shape.isArrowHit((moved[0] + moved[1]) / 2)
    shape.direction = 90
    rotated = shape._rotation_arrow_points()
    assert rotated is not moved
    assert not shape.isArrowHit((moved[0] + moved[1]) / 2)
    assert shape.isArrowHit((rotated[0] + rotated[1]) / 2)
    shape.points = [point + QtCore.QPointF(0, 1000) for point in shape.points]
    replaced = shape._rotation_arrow_points()
    assert replaced is not rotated
    assert shape.isArrowHit((replaced[0] + replaced[1]) / 2)


def test_circle_bounds_use_true_radius_and_empty_point_has_area():
    store = CountingStore(canvas_display_shape_label=False,
                          canvas_display_shape_center_cross=False)
    settings = ShapeRenderSettings.from_store(1, store=store)
    circle = make_shape("circle", [(100, 100), (130, 140)])
    bounds = circle.paintBounds(1, settings)
    assert bounds.contains(QtCore.QRectF(50, 50, 100, 100))
    point = make_shape("point", [(5, 5)])
    assert not point.paintBounds(1, settings).isEmpty()
    assert make_shape("point", []).paintBounds(1, settings).isEmpty()
