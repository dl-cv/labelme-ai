"""验证正式主窗的隔离离屏截图入口。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


def test_offscreen_capture_uses_real_annotation(tmp_path):
    sample = (
        Path(__file__).resolve().parents[3]
        / "examples" / "instance_segmentation" / "data_annotated"
        / "2011_000003.jpg"
    )
    original = (sample.stat().st_size, sample.stat().st_mtime_ns)
    annotation = sample.with_suffix(".json")
    original_annotation = (annotation.stat().st_size, annotation.stat().st_mtime_ns)
    assert sample.is_file() and annotation.is_file()
    output = tmp_path / "screenshots"
    output.mkdir()
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    result = subprocess.run(
        [sys.executable, "-m", "labelme", "--screenshot-output",
         str(output), str(sample)],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "当前语言设置为: zh_CN" in result.stdout
    assert (sample.stat().st_size, sample.stat().st_mtime_ns) == original
    assert (
        annotation.stat().st_size, annotation.stat().st_mtime_ns
    ) == original_annotation
    assert {file.name for file in output.iterdir()} == {
        "主窗口.png", "设置面板.png", "标注页.png"
    }
    for file in output.iterdir():
        with Image.open(file) as image:
            assert image.size[0] > 200 and image.size[1] > 200
            assert image.getbbox() is not None
            if file.name == "主窗口.png":
                assert image.size == (1920, 1080)


def test_offscreen_capture_clears_two_image_group(tmp_path):
    from labelme.dlcv.label_file import LabelFile

    repository = Path(__file__).resolve().parents[3]
    sample = (
        repository / "examples" / "instance_segmentation" / "data_annotated"
        / "2011_000003.jpg"
    )
    annotation = json.loads(sample.with_suffix(".json").read_text(encoding="utf-8"))
    materials = tmp_path / "materials"
    materials.mkdir()
    images = [materials / name for name in ("first.jpg", "second.jpg")]
    for image in images:
        shutil.copy2(sample, image)
    for image in images:
        LabelFile().save(
            filename=str(image.with_suffix(".json")),
            shapes=annotation["shapes"][:1], imagePath=image.name,
            imageHeight=annotation["imageHeight"], imageWidth=annotation["imageWidth"],
            flags={}, otherData={
                "image_path_list": ["first.jpg"], "img_name_list": ["second.jpg"],
            }, save_external_json=True,
        )
    originals = {path: path.read_bytes() for path in materials.iterdir()}
    assert len(originals) == 4
    output = tmp_path / "screenshots"
    output.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    env.update({"TEMP": str(runtime), "TMP": str(runtime),
                "LABELME_LOG_DIR": str(runtime)})
    result = subprocess.run(
        [sys.executable, "-m", "labelme", "--screenshot-output", str(output),
         "--screenshot-clear-group", str(images[0])],
        cwd=repository, env=env, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {path: path.read_bytes() for path in materials.iterdir()} == originals
    assert {path.name for path in output.iterdir()} == {
        "主窗口.png", "设置面板.png", "标注页.png", "清空前主窗口.png", "清空验证.json",
    }
    report = json.loads((output / "清空验证.json").read_text(encoding="utf-8"))
    assert report == {
        "success": True,
        "images": [
            {
                "name": name, "before_label_count": 1, "reopened_label_count": 0,
                "embedded_json_exists": False, "external_json_exists": False,
                "has_label_file": False, "file_tree_checked": False, "success": True,
            }
            for name in ("first.jpg", "second.jpg")
        ],
    }
    for name in ("清空前主窗口.png", "主窗口.png"):
        with Image.open(output / name) as image:
            assert image.size == (1920, 1080)
            assert image.getbbox() is not None
