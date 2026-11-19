"""灰度显示窗的像素、Qt 控件及真实主窗回归。"""
import hashlib
import sys

import cv2
import numpy as np
import pytest
from PIL import Image
from qtpy import QtCore

from labelme.dlcv.widget.gray_window_dock import (
    GrayWindowDock, auto_window, window_to_uint8,
)


def test_window_clips_without_unsigned_wrap_or_mutation():
    raw = np.array([[0, 21299, 21300, 21681, 22062, 65535]], dtype=np.uint16)
    original = raw.copy()
    result = window_to_uint8(raw, 21300, 22062)
    assert result.tolist() == [[0, 0, 0, 127, 255, 255]]
    np.testing.assert_array_equal(raw, original)
    assert result.dtype == np.uint8
    with pytest.raises(ValueError):
        window_to_uint8(raw, 100, 100)


@pytest.mark.parametrize("value", [0, 21300, 65535])
def test_constant_image_has_valid_window(value):
    raw = np.full((8, 8), value, np.uint16)
    low, high = auto_window(raw)
    assert 0 <= low < high <= 65535
    assert window_to_uint8(raw, low, high).shape == raw.shape


def test_auto_ignores_dominant_flat_background():
    raw = np.full((100, 100), 40000, np.uint16)
    raw[:20] = np.arange(2000, dtype=np.uint16).reshape(20, 100) + 21000
    low, high = auto_window(raw)
    assert 21000 <= low < high < 24000


def test_auto_black_level_is_foreground_minimum():
    raw = np.full((100, 100), 40000, np.uint16)
    raw[:20] = np.arange(2000, dtype=np.uint16).reshape(20, 100) + 23317
    low, high = auto_window(raw)
    assert low == 23317
    assert high > low


def test_auto_black_level_excludes_background_below_foreground():
    raw = np.zeros((100, 100), np.uint16)
    raw[:20] = np.arange(2000, dtype=np.uint16).reshape(20, 100) + 23317
    raw[20:40] = 40000
    original = raw.copy()
    low, high = auto_window(raw)
    assert raw.min() == 0
    assert low == 23317
    assert high > low
    np.testing.assert_array_equal(raw, original)


def test_auto_uses_object_peak_instead_of_edge_tail():
    rng = np.random.default_rng(0)
    raw = np.full((400, 400), 40000, np.uint16)
    raw[:80] = np.clip(rng.normal(24500, 200, (80, 400)), 23317, 26000).astype(np.uint16)
    raw[80:100] = rng.integers(26000, 39999, (20, 400), dtype=np.uint16)
    raw[0, 0] = 23317
    low, high = auto_window(raw)
    assert low == 23317
    assert 24700 < high < 26000


def test_crossing_slider_preserves_width_and_precise_input(qtbot):
    dock = GrayWindowDock()
    qtbot.addWidget(dock)
    raw = np.arange(23317, 25317, dtype=np.uint16).reshape(40, 50)
    dock.set_image(raw)
    assert dock.minimum_slider.maximum() - dock.minimum_slider.minimum() < 6000
    width = dock.maximum_spin.value() - dock.minimum_spin.value()
    dock.minimum_spin.setValue(33798)
    assert dock.maximum_spin.value() - dock.minimum_spin.value() == width
    assert dock.minimum_spin.value() == 33798
    assert dock.minimum_slider.value() == 33798
    dock.maximum_spin.setValue(10000)
    assert dock.maximum_spin.value() - dock.minimum_spin.value() == width
    dock.auto_adjust()
    assert dock.minimum_spin.value() == 23317
    assert dock.minimum_slider.maximum() < 30000


def test_slider_reaches_raw_maximum_after_auto_adjust(qtbot):
    dock = GrayWindowDock()
    qtbot.addWidget(dock)
    raw = np.full((100, 100), 40000, np.uint16)
    raw[:20] = np.arange(2000, dtype=np.uint16).reshape(20, 100) + 16296
    dock.set_image(raw)
    for _ in range(2):
        assert dock.maximum_spin.value() < 40000
        assert dock.maximum_slider.minimum() == 16296
        assert dock.maximum_slider.maximum() == 40000
        dock.maximum_slider.setValue(40000)
        assert dock.maximum_spin.value() == 40000
        assert dock.histogram.window[1] == 40000
        dock.auto_adjust()
    dock.maximum_spin.setValue(65535)
    assert dock.maximum_spin.value() == 65535
    assert dock.maximum_slider.value() == 65535


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_histogram_counts_raw_pixels_and_caches_while_adjusting(qtbot, dtype):
    dock = GrayWindowDock()
    qtbot.addWidget(dock)
    raw = np.array([[0, 0, 10], [20, 20, 20]], dtype=dtype)
    original = raw.copy()
    dock.set_image(raw)
    histogram = dock.histogram
    assert histogram.counts.sum() == raw.size
    assert histogram.edges[0] == 0
    assert histogram.edges[-1] == 21
    assert histogram.counts[0] == 2
    assert histogram.counts[10] == 1
    assert histogram.counts[20] == 3
    counts = histogram.counts
    dock.minimum_spin.setValue(5)
    dock.maximum_spin.setValue(18)
    assert histogram.window == (5, 18)
    assert histogram.counts is counts
    np.testing.assert_array_equal(raw, original)
    dock.set_image(None)
    assert histogram.counts is None
    assert histogram.edges is None


def test_histogram_keeps_background_and_handles_constant_image(qtbot):
    dock = GrayWindowDock()
    qtbot.addWidget(dock)
    raw = np.full((100, 100), 40000, np.uint16)
    raw[:20] = np.arange(2000, dtype=np.uint16).reshape(20, 100) + 23317
    dock.set_image(raw)
    assert dock.histogram.counts.sum() == raw.size
    assert dock.histogram.counts[-1] >= 8000
    for value in (0, 65535):
        dock.set_image(np.full((8, 8), value, np.uint16))
        assert dock.histogram.counts.sum() == 64
        assert np.isfinite(dock.histogram._heights).all()
    dock.set_image(np.zeros((3, 3, 3), np.uint8))
    assert dock.histogram.counts is None


def test_dock_controls_and_image_switch(qtbot):
    dock = GrayWindowDock()
    qtbot.addWidget(dock)
    assert not dock.controls.isEnabled()
    raw = np.array([[0, 21300, 22062, 65535]], np.uint16)
    dock.set_image(raw)
    assert dock.raw_image is raw
    dock.minimum_spin.setValue(21300)
    with qtbot.waitSignal(dock.imageChanged, timeout=1000):
        dock.maximum_spin.setValue(22062)
    assert dock.minimum_slider.value() == 21300
    assert dock.maximum_slider.value() == 22062
    assert dock.display_image().tolist() == [[0, 0, 255, 255]]
    dock.minimum_spin.setValue(65535)
    assert dock.minimum_spin.value() < dock.maximum_spin.value()
    dock.maximum_spin.setValue(0)
    assert dock.minimum_spin.value() < dock.maximum_spin.value()
    dock.reset_window()
    assert (dock.minimum_spin.value(), dock.maximum_spin.value()) == (0, 65535)
    dock.set_image(np.zeros((3, 3, 3), np.uint8))
    assert dock.raw_image is None
    assert not dock.controls.isEnabled()
    assert not dock._timer.isActive()
    dock.set_image(np.array([[0, 10, 255]], np.uint8))
    assert dock.display_image().tolist() == [[0, 10, 255]]


@pytest.mark.gui
def test_real_window_preserves_annotations_view_and_raw_tiff(qtbot, monkeypatch, tmp_path):
    from labelme.config import get_config
    from labelme.dlcv.app import MainWindow
    from labelme.dlcv.shape import Shape
    from labelme.dlcv.store import STORE

    monkeypatch.setattr(sys, "argv", ["pytest"])
    monkeypatch.setattr(STORE, "brightness_contrast_values", (1.5, 1.5))
    raw = np.linspace(21000, 23000, 256 * 256).reshape(256, 256).astype(np.uint16)
    path = tmp_path / "窄范围.tif"
    Image.fromarray(raw).save(path)
    original_hash = hashlib.sha256(path.read_bytes()).digest()
    config = get_config()
    config["auto_save"] = False
    config["keep_prev"] = False
    window = MainWindow(config=config)
    qtbot.addWidget(window)
    try:
        assert window.loadFile(str(path)) is not False
        dock = window.gray_window_dock
        from qtpy import QtWidgets

        assert not dock.features() & QtWidgets.QDockWidget.DockWidgetClosable
        assert dock.features() & QtWidgets.QDockWidget.DockWidgetMovable
        assert dock.features() & QtWidgets.QDockWidget.DockWidgetFloatable
        assert dock.toggleViewAction() not in window.menus.view.actions()
        assert not dock.isHidden()
        np.testing.assert_array_equal(dock.raw_image, raw)
        shape = Shape(label="defect", shape_type="rectangle")
        shape.addPoint(QtCore.QPointF(10, 20))
        shape.addPoint(QtCore.QPointF(50, 60))
        shape.close()
        window.loadShapes([shape])
        window.canvas.selectShapes([shape])
        window.canvas.storeShapes()
        window.setDirty()
        window.canvas.scale = 1.5
        window.canvas.offset = QtCore.QPointF(7, 9)
        shapes = window.canvas.shapes[:]
        selected = window.canvas.selectedShapes[:]
        backups = list(window.canvas.shapesBackups)
        dirty = window.dirty
        dock.minimum_spin.setValue(21300)
        with qtbot.waitSignal(dock.imageChanged, timeout=1000):
            dock.maximum_spin.setValue(22062)
        assert window.canvas.shapes == shapes
        assert window.canvas.shapes[0] is shape
        assert window.canvas.selectedShapes == selected
        assert window.canvas.shapesBackups == backups
        assert window.canvas.scale == 1.5
        assert window.canvas.offset == QtCore.QPointF(7, 9)
        assert window.dirty == dirty
        assert window.canvas.pixmap.size() == window.image.size()
        assert window.image.pixelColor(0, 0).red() == 0
        assert window.image.pixelColor(255, 255).red() == 255
        assert hashlib.sha256(path.read_bytes()).digest() == original_hash
        np.testing.assert_array_equal(dock.raw_image, raw)

        # 沿用既有标注保存机制，但不能把显示副本写回 TIFF 像素。
        window.saveLabels(str(path.with_suffix(".json")))
        decoded = cv2.imdecode(np.fromfile(str(path), np.uint8), -1)
        np.testing.assert_array_equal(decoded, raw)
        assert decoded.dtype == np.uint16
        window.setClean()
        color = tmp_path / "color.png"
        Image.new("RGB", (32, 32), (20, 40, 60)).save(color)
        window.loadFile(str(color))
        assert dock.raw_image is None
        assert not dock.controls.isEnabled()
        window.resetState()
        assert not dock.controls.isEnabled()
    finally:
        window.setClean()
        window.close()
