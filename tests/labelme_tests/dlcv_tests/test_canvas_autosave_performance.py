"""A real MainWindow saves the final rotation edit only once, on release."""

import json
import sys
from unittest.mock import Mock

import pytest
from PIL import Image
from qtpy import QtCore, QtGui


def _mouse(canvas, event_type, position, buttons):
    event = QtGui.QMouseEvent(
        event_type, QtCore.QPointF(*position),
        QtCore.Qt.NoButton if event_type == QtCore.QEvent.MouseMove else QtCore.Qt.LeftButton,
        buttons, QtCore.Qt.NoModifier,
    )
    handler = {
        QtCore.QEvent.MouseButtonPress: canvas.mousePressEvent,
        QtCore.QEvent.MouseMove: canvas.mouseMoveEvent,
        QtCore.QEvent.MouseButtonRelease: canvas.mouseReleaseEvent,
    }[event_type]
    handler(event)


@pytest.mark.parametrize("kind", ["vertex", "arrow"])
def test_rotation_release_autosaves_final_geometry_and_direction(qapp, tmp_path, monkeypatch, kind):
    from dlcv_core.image_json import read_image_json
    from labelme.config import get_config
    from labelme.dlcv.app import MainWindow
    from labelme.dlcv.shape import Shape
    from labelme.dlcv.store import STORE

    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    previous_window = getattr(STORE, "_Store__main_window", None)
    image_path = tmp_path / "rotation.png"
    annotation_path = image_path.with_suffix(".json")
    Image.new("RGB", (800, 600), (30, 40, 50)).save(image_path)
    config = get_config()
    config.update(auto_save=True, store_data=False, keep_prev=False)
    window = None
    try:
        window = MainWindow(config=config, filename=str(image_path))
        qapp.processEvents()
        window.parameter.child("label_setting", "display_rotation_arrow").setValue(True)
        canvas = window.canvas
        canvas.scale = 1.0
        monkeypatch.setattr(Shape, "scale", 1.0)
        canvas.resize(800, 600)
        canvas.offset = QtCore.QPointF()
        shape = Shape(label="component", shape_type="rotation", direction=0, flags={},
                      points=[[100, 100], [200, 100], [200, 160], [100, 160]])
        window.loadShapes([shape])
        assert window.saveLabels(str(annotation_path))
        baseline = annotation_path.read_bytes()
        save = Mock(wraps=window.saveLabels)
        snapshot = Mock(wraps=canvas.storeShapes)
        monkeypatch.setattr(window, "saveLabels", save)
        monkeypatch.setattr(canvas, "storeShapes", snapshot)
        start = (100, 100) if kind == "vertex" else (210, 130)
        _mouse(canvas, QtCore.QEvent.MouseMove, start, QtCore.Qt.NoButton)
        _mouse(canvas, QtCore.QEvent.MouseButtonPress, start, QtCore.Qt.LeftButton)
        if kind == "arrow":
            assert canvas.draggingArrow
        else:
            assert canvas.selectedVertex()
        positions = [(90, 90), (80, 80)] if kind == "vertex" else [(230, 150), (200, 200)]
        for position in positions:
            _mouse(canvas, QtCore.QEvent.MouseMove, position, QtCore.Qt.LeftButton)
            save.assert_not_called()
            snapshot.assert_not_called()
            assert annotation_path.read_bytes() == baseline
        final = (75, 75) if kind == "vertex" else (150, 230)
        _mouse(canvas, QtCore.QEvent.MouseButtonRelease, final, QtCore.Qt.NoButton)
        assert save.call_count == 1
        snapshot.assert_called_once_with()
        external = json.loads(annotation_path.read_text(encoding="utf-8"))
        assert external == read_image_json(image_path)
        saved = external["shapes"][0]
        assert saved["points"] == [[point.x(), point.y()] for point in shape.points]
        assert saved["direction"] == shape.direction
        assert saved["direction"] == pytest.approx(0 if kind == "vertex" else 90)
        assert not window.dirty
        assert len(canvas.shapesBackups) == 2
        # The external/embedded data remains the actual source when reopening.
        window.loadFile(str(image_path))
        reopened = window.canvas.shapes[0]
        assert [[point.x(), point.y()] for point in reopened.points] == saved["points"]
        assert reopened.direction == saved["direction"]
    finally:
        if window is not None:
            window.setClean()
            window.close()
            window.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(window, QtCore.QEvent.DeferredDelete)
        STORE.register_main_window(previous_window)
