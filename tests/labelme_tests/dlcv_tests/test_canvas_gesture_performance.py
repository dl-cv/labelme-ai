"""Rotation editing commits once per gesture, using the real offscreen canvas."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from labelme.dlcv import canvas as canvas_module
from labelme.dlcv import shape as shape_module
from labelme.dlcv.canvas import Canvas
from labelme.dlcv.shape import Shape


@pytest.fixture(scope="module")
def gesture_qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def _geometry(shape):
    return tuple((point.x(), point.y()) for point in shape.points), shape.direction


def _rotation_shape():
    return Shape(
        label="component",
        shape_type="rotation",
        points=[[100.0, 100.0], [200.0, 100.0], [200.0, 160.0], [100.0, 160.0]],
        direction=0.0,
    )


@pytest.fixture
def gesture_canvas(gesture_qapp, monkeypatch):
    settings = SimpleNamespace(
        canvas_brush_enabled=True,
        canvas_display_rotation_arrow=True,
        canvas_display_shape_label=False,
        canvas_display_shape_center_cross=False,
        canvas_highlight_start_point=False,
    )
    monkeypatch.setattr(canvas_module, "STORE", settings)
    monkeypatch.setattr(shape_module, "STORE", settings)
    monkeypatch.setattr(Shape, "scale", 1.0)
    canvas = Canvas()
    canvas.resize(400, 300)
    pixmap = QtGui.QPixmap(400, 300)
    pixmap.fill(QtCore.Qt.white)
    canvas.loadPixmap(pixmap)

    # MainWindow normally mirrors this signal back into the canvas selection.
    def select_shapes(shapes):
        for shape in canvas.shapes:
            shape.selected = shape in shapes
        canvas.selectedShapes = list(shapes)

    canvas.selectionChanged.connect(select_shapes)
    shape = _rotation_shape()
    canvas.loadShapes([shape])
    store = Mock(wraps=canvas.storeShapes)
    monkeypatch.setattr(canvas, "storeShapes", store)
    commits = []
    canvas.shapeMoved.connect(lambda: commits.append(_geometry(shape)))
    yield SimpleNamespace(canvas=canvas, shape=shape, store=store, commits=commits)
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()
    canvas.close()
    canvas.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)


def _mouse(canvas, event_type, point):
    is_move = event_type == QtCore.QEvent.MouseMove
    is_release = event_type == QtCore.QEvent.MouseButtonRelease
    event = QtGui.QMouseEvent(
        event_type,
        QtCore.QPointF(*point),
        QtCore.Qt.NoButton if is_move else QtCore.Qt.LeftButton,
        QtCore.Qt.NoButton if is_release else QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    handlers = {
        QtCore.QEvent.MouseButtonPress: canvas.mousePressEvent,
        QtCore.QEvent.MouseMove: canvas.mouseMoveEvent,
        QtCore.QEvent.MouseButtonRelease: canvas.mouseReleaseEvent,
    }
    handlers[event_type](event)


def _begin(harness, kind):
    canvas = harness.canvas
    start = (100, 100) if kind == "vertex" else (210, 130)
    # Real hover establishes the vertex highlight used by mousePressEvent.
    hover = QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove,
        QtCore.QPointF(*start),
        QtCore.Qt.NoButton,
        QtCore.Qt.NoButton,
        QtCore.Qt.NoModifier,
    )
    canvas.mouseMoveEvent(hover)
    if kind == "vertex":
        assert canvas.hShape is harness.shape
        assert canvas.hVertex == 0
    _mouse(canvas, QtCore.QEvent.MouseButtonPress, start)
    return start


def _move_points(kind):
    return [(90, 90), (80, 80)] if kind == "vertex" else [(230, 150), (200, 200)]


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
def test_rotation_moves_do_not_snapshot_or_emit_until_release(gesture_canvas, kind):
    harness = gesture_canvas
    original = _geometry(harness.shape)
    _begin(harness, kind)
    for point in _move_points(kind):
        _mouse(harness.canvas, QtCore.QEvent.MouseMove, point)
        assert _geometry(harness.shape) != original
        harness.store.assert_not_called()
        assert harness.commits == []
        assert len(harness.canvas.shapesBackups) == 1

    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, point)
    harness.store.assert_called_once_with()
    assert harness.commits == [_geometry(harness.shape)]
    assert len(harness.canvas.shapesBackups) == 2
    assert _geometry(harness.canvas.shapesBackups[-1][0]) == _geometry(harness.shape)

    # A duplicated release must not add an undo step or save again.
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, point)
    harness.store.assert_called_once_with()
    assert len(harness.commits) == 1


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
def test_rotation_release_uses_final_mouse_position(gesture_canvas, kind):
    harness = gesture_canvas
    _begin(harness, kind)
    _mouse(harness.canvas, QtCore.QEvent.MouseMove, _move_points(kind)[0])
    intermediate = _geometry(harness.shape)
    final = (75, 75) if kind == "vertex" else (150, 230)
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, final)

    assert _geometry(harness.shape) != intermediate
    if kind == "vertex":
        assert harness.shape.points[0] == QtCore.QPointF(75, 75)
        assert harness.shape.direction == 0.0
    else:
        assert harness.shape.direction == pytest.approx(90.0)
        assert harness.shape.points[0].x() == pytest.approx(180.0)
        assert harness.shape.points[0].y() == pytest.approx(80.0)
    harness.store.assert_called_once_with()
    assert harness.commits == [_geometry(harness.shape)]


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
@pytest.mark.parametrize("same_position_move", [False, True])
def test_unchanged_rotation_gesture_does_not_commit(
    gesture_canvas, kind, same_position_move
):
    harness = gesture_canvas
    original = _geometry(harness.shape)
    start = _begin(harness, kind)
    if same_position_move:
        _mouse(harness.canvas, QtCore.QEvent.MouseMove, start)
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, start)

    assert _geometry(harness.shape) == original
    harness.store.assert_not_called()
    assert harness.commits == []
    assert len(harness.canvas.shapesBackups) == 1


def test_unchanged_diagonal_rotation_vertex_does_not_commit(gesture_canvas):
    harness = gesture_canvas
    harness.shape.points = [
        QtCore.QPointF(x, y)
        for x, y in [(150, 60), (220, 130), (150, 200), (80, 130)]
    ]
    harness.shape.direction = 45.0
    harness.canvas.shapesBackups.clear()
    harness.canvas.storeShapes()
    harness.store.reset_mock()
    original = _geometry(harness.shape)
    start = (150, 60)
    hover = QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove,
        QtCore.QPointF(*start),
        QtCore.Qt.NoButton,
        QtCore.Qt.NoButton,
        QtCore.Qt.NoModifier,
    )
    harness.canvas.mouseMoveEvent(hover)
    assert harness.canvas.hShape is harness.shape
    assert harness.canvas.hVertex == 0
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonPress, start)
    _mouse(harness.canvas, QtCore.QEvent.MouseMove, start)
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, start)

    assert _geometry(harness.shape) == original
    harness.store.assert_not_called()
    assert harness.commits == []
    assert len(harness.canvas.shapesBackups) == 1


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
def test_one_undo_restores_points_and_direction(gesture_canvas, kind):
    harness = gesture_canvas
    original = _geometry(harness.shape)
    _begin(harness, kind)
    for point in _move_points(kind):
        _mouse(harness.canvas, QtCore.QEvent.MouseMove, point)
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, point)

    assert _geometry(harness.shape) != original
    assert harness.canvas.isShapeRestorable
    assert len(harness.canvas.shapesBackups) == 2
    harness.canvas.restoreShape()
    assert _geometry(harness.canvas.shapes[0]) == original
    assert harness.canvas.shapes[0] is not harness.shape


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
@pytest.mark.parametrize("late_move", [False, True])
def test_focus_loss_commits_once_and_late_events_are_ignored(
    gesture_canvas, kind, late_move
):
    harness = gesture_canvas
    _begin(harness, kind)
    for point in _move_points(kind):
        _mouse(harness.canvas, QtCore.QEvent.MouseMove, point)
    moved = _geometry(harness.shape)
    harness.store.assert_not_called()
    assert harness.commits == []

    harness.canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    harness.store.assert_called_once_with()
    assert harness.commits == [moved]
    assert len(harness.canvas.shapesBackups) == 2

    final = (75, 75) if kind == "vertex" else (150, 230)
    if late_move:
        _mouse(harness.canvas, QtCore.QEvent.MouseMove, final)
        assert _geometry(harness.shape) == moved
        harness.store.assert_called_once_with()
        assert harness.commits == [moved]
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, final)
    harness.canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert _geometry(harness.shape) == moved
    harness.store.assert_called_once_with()
    assert harness.commits == [moved]


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
def test_focus_loss_before_first_move_discards_late_events(gesture_canvas, kind):
    harness = gesture_canvas
    original = _geometry(harness.shape)
    _begin(harness, kind)
    harness.canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    harness.store.assert_not_called()
    assert harness.commits == []

    final = (75, 75) if kind == "vertex" else (150, 230)
    _mouse(harness.canvas, QtCore.QEvent.MouseMove, final)
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, final)
    assert _geometry(harness.shape) == original
    harness.store.assert_not_called()
    assert harness.commits == []
    assert len(harness.canvas.shapesBackups) == 1


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
@pytest.mark.parametrize("operation", ["reset", "load_shapes", "load_pixmap"])
@pytest.mark.parametrize("late_move", [False, True])
def test_reset_and_load_discard_pending_rotation_gesture(
    gesture_canvas, kind, operation, late_move
):
    harness = gesture_canvas
    _begin(harness, kind)
    _mouse(harness.canvas, QtCore.QEvent.MouseMove, _move_points(kind)[0])
    old_geometry = _geometry(harness.shape)
    harness.store.assert_not_called()
    assert harness.commits == []

    replacement = None
    if operation == "reset":
        harness.canvas.resetState()
    elif operation == "load_shapes":
        replacement = _rotation_shape()
        harness.canvas.loadShapes([replacement])
    else:
        pixmap = QtGui.QPixmap(400, 300)
        pixmap.fill(QtCore.Qt.white)
        harness.canvas.loadPixmap(pixmap)
    # loadShapes creates its own baseline; only a stale gesture commit is forbidden.
    harness.store.reset_mock()
    backup_count = len(harness.canvas.shapesBackups)
    final = (75, 75) if kind == "vertex" else (150, 230)
    if late_move:
        _mouse(harness.canvas, QtCore.QEvent.MouseMove, final)
        assert _geometry(harness.shape) == old_geometry
        harness.store.assert_not_called()
        assert harness.commits == []
    _mouse(harness.canvas, QtCore.QEvent.MouseButtonRelease, final)
    harness.canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))

    harness.store.assert_not_called()
    assert harness.commits == []
    assert len(harness.canvas.shapesBackups) == backup_count
    assert _geometry(harness.shape) == old_geometry
    if replacement is not None:
        assert harness.canvas.shapes == [replacement]
        assert _geometry(replacement) == _geometry(_rotation_shape())
    if operation == "load_pixmap":
        assert harness.canvas.shapes == []
