"""AI 模块导入时保留模型导出，并延迟加载下载和驱动库。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("module_name", ["labelme.ai", "labelme.dlcv.ai"])
def test_ai_import_keeps_exports_without_download_or_driver_libraries(module_name):
    code = """
import importlib
import sys

module = importlib.import_module(sys.argv[1])
sys.excepthook = sys.__excepthook__
exports = {}
exec("from " + sys.argv[1] + " import *", exports)
for name in ("SegmentAnythingModelVitB", "SegmentAnythingModelVitL",
             "SegmentAnythingModelVitH", "EfficientSamVitT", "EfficientSamVitS"):
    model = getattr(module, name)
    assert isinstance(model, type), name
    assert exports[name] is model, name
assert module.MODELS == [module.EfficientSamVitS]
for name in ("get_rectangles_from_texts", "get_shapes_from_annotations",
             "non_maximum_suppression"):
    assert callable(exports[name]), name
for name in ("gdown", "pynvml", "imgviz", "matplotlib"):
    assert not any(key == name or key.startswith(name + ".")
                   for key in sys.modules), name
"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code, module_name],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_app_import_defers_original_color_shuffle_until_first_use():
    import imgviz

    code = f"""
import sys
import numpy as np

expected = np.array({imgviz.label_colormap().tolist()!r}, dtype=np.uint8)
np.random.seed(12345)
np.random.shuffle(expected)
expected_state = np.random.get_state()
np.random.seed(12345)
import labelme.dlcv.app
import labelme.app
import labelme.dlcv.canvas
sys.excepthook = sys.__excepthook__
assert labelme.app.MODELS == [labelme.dlcv.ai.EfficientSamVitS]
assert labelme.app.Canvas is labelme.dlcv.canvas.Canvas
for name in ("gdown", "pynvml", "imgviz", "matplotlib"):
    assert not any(key == name or key.startswith(name + ".")
                   for key in sys.modules), name
colormap = labelme.app.get_label_colormap()
assert labelme.dlcv.app.get_label_colormap() is colormap
assert colormap.dtype == expected.dtype
np.testing.assert_array_equal(colormap, expected)
actual_state = np.random.get_state()
assert actual_state[0] == expected_state[0]
np.testing.assert_array_equal(actual_state[1], expected_state[1])
assert actual_state[2:] == expected_state[2:]
"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sam_resize_matches_installed_imgviz():
    import imgviz
    import numpy as np

    from labelme.ai.segment_anything_model import _resize_image

    image = np.arange(45, dtype=np.uint8).reshape(3, 5, 3)
    scale, actual = _resize_image(image_size=8, image=image)
    expected = imgviz.resize(image, height=5, width=8, backend="pillow")
    assert scale == 8 / 5
    assert actual.dtype == np.float32
    np.testing.assert_array_equal(actual, expected.astype(np.float32))


@pytest.mark.parametrize("embedded", [False, True])
def test_label_sanity_reads_real_image(tmp_path, embedded):
    from PIL import Image

    from labelme.testing import assert_labelfile_sanity
    from labelme.utils import img_arr_to_b64

    image = Image.new("RGB", (5, 3), color=(10, 20, 30))
    image.save(tmp_path / "sample.png")
    data = {
        "imagePath": "sample.png",
        "imageHeight": 3,
        "imageWidth": 5,
        "shapes": [],
    }
    if embedded:
        import numpy as np

        data["imageData"] = img_arr_to_b64(np.asarray(image))
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert_labelfile_sanity(str(path))
    data["imageWidth"] = 6
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AssertionError):
        assert_labelfile_sanity(str(path))
