"""PNG 正式采图的设置隔离、禁止保存及外部标注读取检查。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from dlcv_core.image_json import read_image_json, write_image_json
from PIL import Image


CAPTURE_CHECK = r'''
import os
import sys
from pathlib import Path
from qtpy import QtCore

runtime = Path(os.environ["TEMP"]).resolve()
settings_files = []
settings_class = QtCore.QSettings

class CaptureSettings(settings_class):
    def __init__(self, *args, **kwargs):
        assert len(args) == 2 and args[1] == settings_class.IniFormat, args
        path = Path(args[0]).resolve()
        assert path.is_relative_to(runtime), path
        assert path.relative_to(runtime).parts[0].startswith("labelme-ui-"), path
        super().__init__(*args, **kwargs)
        assert self.format() == settings_class.IniFormat
        assert Path(self.fileName()).resolve() == path
        settings_files.append(path)

QtCore.QSettings = CaptureSettings
QtCore.QSettings.setDefaultFormat(settings_class.NativeFormat)
from labelme import __main__ as entry
from dlcv_core.image_json import read_image_json

calls = []
sentinel = object()
def recorded_settings(*args):
    calls.append(args)
    return sentinel
QtCore.QSettings = recorded_settings
for organization, application in (("labelme", "labelme"), ("baiduyun_dev", "ai")):
    assert entry.MainWindow.createSettings(None, organization, application) is sentinel
assert calls == [("labelme", "labelme"), ("baiduyun_dev", "ai")]
QtCore.QSettings = CaptureSettings

original_config = entry.get_config
original_load = entry.MainWindow.loadFile
original_close = entry.MainWindow.closeEvent
loads = []
closed = []
expected = ["外部标注"] if sys.argv[3] == "annotated" else []

def autosaving_config(*args, **kwargs):
    config = original_config(*args, **kwargs)
    config["auto_save"] = True
    return config

def observed_load(window, filename=None):
    assert window._config["auto_save"] is False
    assert not window.actions.saveAuto.isChecked()
    result = original_load(window, filename)
    assert result and not window.canvas.pixmap.isNull()
    assert [shape.label for shape in window.canvas.shapes] == expected
    copied = Path(window.filename)
    assert read_image_json(copied)["shapes"][0]["label"] == "图内诱饵"
    if sys.argv[3] == "missing":
        assert not copied.with_suffix(".json").exists()
        assert window.labelFile is None
    else:
        assert window.labelFile.flags == {"外部标志": True}
    loads.append(copied)
    return result

def observed_close(window, event):
    for settings in (window.settings, window.dev_setting):
        assert settings.format() == settings_class.IniFormat
        assert Path(settings.fileName()).resolve() in settings_files
    original_close(window, event)
    window.settings.sync()
    assert window.settings.status() == settings_class.NoError
    closed.append(event.isAccepted())

def forbidden_save(*args, **kwargs):
    raise AssertionError("只读采图不得保存标注")

entry.get_config = autosaving_config
entry.MainWindow.loadFile = observed_load
entry.MainWindow.closeEvent = observed_close
entry.MainWindow.saveFile = forbidden_save
entry.MainWindow.saveLabels = forbidden_save
entry.render_screenshots(sys.argv[1], Path(sys.argv[2]))
assert loads and closed == [True]
assert settings_files
print("capture_checked:", sys.argv[3])
'''


@pytest.mark.parametrize("annotation", ["annotated", "empty", "missing"])
def test_png_capture_is_isolated_and_readonly(tmp_path, annotation):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (48, 32), (20, 80, 160)).save(image_path)
    shape = {
        "label": "图内诱饵", "points": [[2, 2], [20, 2], [20, 20], [2, 20]],
        "shape_type": "polygon", "flags": {}, "group_id": None,
        "description": "", "mask": None,
    }
    data = {
        "version": "5.0.1", "imagePath": image_path.name, "imageData": None,
        "imageWidth": 48, "imageHeight": 32, "shapes": [shape], "flags": {},
    }
    write_image_json(image_path, data)
    assert read_image_json(image_path)["shapes"] == [shape]
    if annotation != "missing":
        external_json = {**data, "flags": {"外部标志": True}, "shapes": []}
        if annotation == "annotated":
            external_json["shapes"] = [{**shape, "label": "外部标注"}]
        image_path.with_suffix(".json").write_text(
            json.dumps(external_json, ensure_ascii=False), encoding="utf-8",
        )
    originals = {path: path.read_bytes() for path in tmp_path.iterdir()}
    output = tmp_path / "screenshots"
    output.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = os.environ.copy()
    env.update({
        "TEMP": str(runtime), "TMP": str(runtime), "TMPDIR": str(runtime),
        "LABELME_LOG_DIR": str(runtime), "QT_QPA_PLATFORM": "offscreen",
        "QT_OPENGL": "software", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "CUDA_VISIBLE_DEVICES": "-1",
    })
    result = subprocess.run(
        [sys.executable, "-B", "-c", CAPTURE_CHECK, str(image_path), str(output),
         annotation], cwd=runtime, env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=90,
    )
    (tmp_path / "capture.log").write_text(
        result.stdout + result.stderr, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"capture_checked: {annotation}" in result.stdout
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert image_path.with_suffix(".json").exists() == (annotation != "missing")
    assert {path.name for path in output.iterdir()} == {
        "主窗口.png", "设置面板.png", "标注页.png",
    }
    for path in output.iterdir():
        with Image.open(path) as image:
            assert image.width > 200 and image.height > 200
            assert image.getbbox() is not None
