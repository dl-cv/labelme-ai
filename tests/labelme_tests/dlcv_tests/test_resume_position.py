"""断点续标（按文件夹恢复上次图片）的存储与主窗口集成检查。"""

import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from labelme.config import get_config
from labelme.dlcv.app import MainWindow
from labelme.dlcv.controller.resume_position import ResumePositionStore


class _FakeSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


def _create_images(directory: Path, count: int):
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        path = directory / f"defect_{index:03d}.png"
        Image.new("RGB", (320, 240), (index * 10, 80, 160)).save(path)
        paths.append(path)
    return paths


def _expected_path(path):
    return os.path.normpath(os.path.abspath(path))


def _create_window(qtbot):
    config = get_config()
    config["auto_save"] = False
    window = MainWindow(config=config)
    qtbot.addWidget(window)
    return window


def test_store_remembers_and_restores_per_directory(tmp_path):
    first_dir = tmp_path / "batch_a"
    first_images = _create_images(first_dir, 3)
    second_dir = tmp_path / "batch_b"
    second_images = _create_images(second_dir, 1)

    settings = _FakeSettings()
    store = ResumePositionStore(settings)
    assert store.get(first_dir) is None

    assert store.remember(first_images[1]) is True
    assert store.remember(second_images[0]) is True
    assert store.get(first_dir) == _expected_path(first_images[1])
    assert store.get(second_dir) == _expected_path(second_images[0])

    # 持久化后，新建的 store 仍然可以恢复。
    store.persist()
    restored = ResumePositionStore(settings)
    assert restored.get(first_dir) == _expected_path(first_images[1])
    assert restored.get(second_dir) == _expected_path(second_images[0])

    # 文件被删除后不再返回失效路径。
    first_images[1].unlink()
    restored.forget(first_dir)
    assert restored.get(first_dir) is None


def test_store_limits_directory_count(tmp_path):
    settings = _FakeSettings()
    store = ResumePositionStore(settings, max_dirs=2)
    directories = []
    for index in range(3):
        directory = tmp_path / f"batch_{index}"
        images = _create_images(directory, 1)
        directories.append((directory, images[0]))
        assert store.remember(images[0]) is True

    assert store.get(directories[0][0]) is None
    assert store.get(directories[1][0]) == _expected_path(directories[1][1])
    assert store.get(directories[2][0]) == _expected_path(directories[2][1])


def test_remember_ignores_missing_file(tmp_path):
    settings = _FakeSettings()
    store = ResumePositionStore(settings)
    assert store.remember(tmp_path / "not_exists.png") is False
    assert store.get(tmp_path) is None


@pytest.mark.gui
def test_open_directory_restores_last_image(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["pytest"])
    directory = tmp_path / "batch"
    images = _create_images(directory, 3)

    window = _create_window(qtbot)
    try:
        window.importDirImages(str(directory))
        item = window.fileListWidget.select_file_path(str(images[1]))
        assert item is not None
        assert Path(window.filename).name == images[1].name
        window.setClean()
        window.settings.sync()
    finally:
        window.close()
        window.settings.sync()

    second = _create_window(qtbot)
    try:
        second.importDirImages(str(directory))
        assert second.filename is not None
        assert Path(second.filename).name == images[1].name

        second.setClean()
        second._resume_controller.start_from_first_image()
        assert Path(second.filename).name == images[0].name
    finally:
        second.setClean()
        second.close()


@pytest.mark.gui
def test_open_directory_restores_image_in_subfolder(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["pytest"])
    directory = tmp_path / "batch"
    nested = directory / "line_a"
    images = _create_images(nested, 3)

    window = _create_window(qtbot)
    try:
        window.importDirImages(str(directory))
        assert window.fileListWidget.select_file_path(str(images[2])) is not None
        assert Path(window.filename).name == images[2].name
        window.setClean()
        window.settings.sync()
    finally:
        window.close()
        window.settings.sync()

    second = _create_window(qtbot)
    try:
        second.importDirImages(str(directory))
        assert second.filename is not None
        assert Path(second.filename).name == images[2].name
    finally:
        second.setClean()
        second.close()


@pytest.mark.gui
def test_open_other_directory_keeps_its_own_position(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["pytest"])
    first_dir = tmp_path / "batch_a"
    first_images = _create_images(first_dir, 2)
    second_dir = tmp_path / "batch_b"
    second_images = _create_images(second_dir, 2)

    window = _create_window(qtbot)
    try:
        window.importDirImages(str(first_dir))
        window.fileListWidget.select_file_path(str(first_images[1]))
        window.setClean()
        window.settings.sync()

        window.importDirImages(str(second_dir))
        window.fileListWidget.select_file_path(str(second_images[0]))
        window.setClean()
        window.settings.sync()

        # 回到第一个文件夹时恢复到它自己的上次位置。
        window.importDirImages(str(first_dir))
        assert Path(window.filename).name == first_images[1].name
        window.setClean()
        window.settings.sync()
    finally:
        window.setClean()
        window.close()
