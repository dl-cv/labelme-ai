"""验证正式主窗的隔离离屏截图入口。"""
import os
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
