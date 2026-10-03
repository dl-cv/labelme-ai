"""正式主窗的外部标注读取、切图及保存检查。"""

import shutil
from pathlib import Path

import pytest

from labelme.config import get_config
from labelme.dlcv.app import MainWindow
from labelme.testing import assert_labelfile_sanity


@pytest.fixture
def sample_data(tmp_path):
    examples = Path(__file__).resolve().parents[2] / "examples"
    annotated = tmp_path / "annotated"
    shutil.copytree(examples / "instance_segmentation" / "data_annotated", annotated)
    tutorial = tmp_path / "tutorial"
    tutorial.mkdir()
    for name in ("apc2016_obj3.jpg", "apc2016_obj3.json"):
        shutil.copy2(examples / "tutorial" / name, tutorial / name)
    raw = tmp_path / "raw"
    raw.mkdir()
    for image_path in annotated.glob("*.jpg"):
        shutil.copy2(image_path, raw / image_path.name)
    return tmp_path


@pytest.fixture
def create_window(qtbot):
    windows = []

    def create(**kwargs):
        config = get_config()
        config["auto_save"] = False
        config["keep_prev"] = False
        window = MainWindow(config=config, **kwargs)
        window.actions.saveAuto.setChecked(False)
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield create
    for window in windows:
        window.setClean()


def _show_and_wait_image(qtbot, window):
    window.show()
    qtbot.waitUntil(lambda: not window.image.isNull())
    window.setClean()


@pytest.mark.gui
def test_MainWindow_open(create_window):
    window = create_window()
    window.show()
    window.close()


@pytest.mark.gui
def test_MainWindow_open_img(qtbot, create_window, sample_data):
    image_path = sample_data / "raw" / "2011_000003.jpg"
    window = create_window(filename=str(image_path))
    _show_and_wait_image(qtbot, window)
    assert window.filename == str(image_path)
    assert window.canvas.shapes == []


@pytest.mark.gui
def test_MainWindow_open_json(qtbot, create_window, sample_data):
    for image_path in (
        sample_data / "tutorial" / "apc2016_obj3.jpg",
        sample_data / "annotated" / "2011_000003.jpg",
    ):
        assert_labelfile_sanity(str(image_path.with_suffix(".json")))
        window = create_window(filename=str(image_path))
        _show_and_wait_image(qtbot, window)
        assert window.labelFile is not None
        assert window.canvas.shapes
        window.setClean()
        window.close()


def create_MainWindow_with_directory(qtbot, create_window, sample_data):
    directory = sample_data / "raw"
    window = create_window()
    window.importDirImages(str(directory), load=False)
    window.loadFile(window.imageList[0])
    _show_and_wait_image(qtbot, window)
    return window


@pytest.mark.gui
def test_MainWindow_openNextImg(qtbot, create_window, sample_data):
    window = create_MainWindow_with_directory(qtbot, create_window, sample_data)
    first_path = window.filename
    window.setClean()
    window.openNextImg()
    assert window.filename != first_path
    assert not window.image.isNull()
    window.setClean()


@pytest.mark.gui
def test_MainWindow_openPrevImg(qtbot, create_window, sample_data):
    window = create_MainWindow_with_directory(qtbot, create_window, sample_data)
    first_path = window.filename
    window.setClean()
    window.openNextImg()
    window.setClean()
    window.openPrevImg()
    assert window.filename == first_path
    assert not window.image.isNull()
    window.setClean()


@pytest.mark.gui
def test_MainWindow_annotate_jpg(qtbot, create_window, sample_data):
    image_path = sample_data / "raw" / "2011_000003.jpg"
    output_path = image_path.with_suffix(".json")
    window = create_window(filename=str(image_path), output_file=str(output_path))
    _show_and_wait_image(qtbot, window)
    window.loadLabels(
        [
            dict(
                label="whole",
                group_id=None,
                points=[(100, 100), (100, 238), (400, 238), (400, 100)],
                shape_type="polygon",
                mask=None,
                flags={},
                other_data={},
            )
        ]
    )
    window.saveFile()
    assert_labelfile_sanity(str(output_path))
