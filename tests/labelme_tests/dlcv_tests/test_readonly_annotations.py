"""2026-10-09：图片内嵌写入被拒绝，外部备份不能代替保存成功。
使用真实文件属性和系统句柄检查失败、备份及原始异常，保持原有保存规则。
"""

import json
import os
import stat
from contextlib import contextmanager

import pytest
from PIL import Image
from dlcv_core.image_json import read_image_json

from labelme.dlcv.label_file import LabelFile, LabelFileError

pytestmark = pytest.mark.skipif(os.name != "nt", reason="使用 Windows 只读文件属性")


def make_shape(label):
    return {"label": label, "points": [[1, 1], [12, 1], [12, 10], [1, 10]],
            "shape_type": "polygon", "flags": {}, "group_id": None, "mask": None}


def save_annotation(image, label, **kwargs):
    label_file = LabelFile()
    label_file.save(str(image.with_suffix(".json")), [make_shape(label)], image.name,
                    16, 24, **kwargs)
    return label_file


@contextmanager
def readonly_file(path):
    original_mode = path.stat().st_mode
    path.chmod(stat.S_IREAD)
    try:
        yield
    finally:
        path.chmod(original_mode)


@pytest.mark.parametrize("extension", [".jpg", ".png"])
@pytest.mark.parametrize("save_external_json", [False, True])
def test_readonly_image_save_reports_failure_despite_external_backup(
    tmp_path, extension, save_external_json
):
    """2026-10-09：外部文件写入不能代替内嵌成功；检查失败及原图保留。"""
    image = tmp_path / ("只读图片" + extension)
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    original = image.read_bytes()
    with readonly_file(image):
        for label in ("首次标注", "最新标注"):
            with pytest.raises(LabelFileError, match="已更新 0 张图片") as error:
                save_annotation(image, label, save_external_json=save_external_json)
            assert isinstance(error.value.__cause__.__cause__, PermissionError)
            sidecar = image.with_suffix(".json")
            assert json.loads(sidecar.read_text(encoding="utf-8"))["shapes"][0]["label"] == label
            assert image.read_bytes() == original
            assert image.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
            assert read_image_json(image) is None


def test_readonly_existing_identical_embedded_annotation_still_reports_failure(tmp_path):
    """2026-10-09：即使内容相同，实际内嵌写入失败也不能改判成功。"""
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    save_annotation(image, "原标注")
    original = image.read_bytes()
    with readonly_file(image):
        with pytest.raises(LabelFileError, match="Permission denied"):
            save_annotation(image, "原标注")
        assert image.read_bytes() == original
        assert LabelFile(str(image)).shapes[0]["label"] == "原标注"


def test_readonly_stale_embedded_annotation_still_reports_failure(tmp_path):
    """2026-10-09：图片无法更新时仍报告失败，最新修改仅保存为外部备份。"""
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    save_annotation(image, "旧标注")
    original = image.read_bytes()
    with readonly_file(image), pytest.raises(LabelFileError, match="最新标注已保存至外部 JSON"):
        save_annotation(image, "最新标注")
    assert image.read_bytes() == original
    assert read_image_json(image)["shapes"][0]["label"] == "旧标注"
    assert json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))["shapes"][0]["label"] == "最新标注"


def test_readonly_sidecar_write_failure_is_not_treated_as_saved(tmp_path):
    """2026-10-09：内嵌和外部备份都不可写时报告失败，不修改原文件。"""
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    sidecar = image.with_suffix(".json")
    sidecar.write_text('{"shapes": []}', encoding="utf-8")
    original = sidecar.read_bytes()
    with readonly_file(image), readonly_file(sidecar), pytest.raises(LabelFileError):
        save_annotation(image, "最新标注")
    assert sidecar.read_bytes() == original
    assert read_image_json(image) is None


def test_group_with_readonly_image_reports_partial_failure(tmp_path):
    """2026-10-09：组保存按各图内嵌结果报告；保留其他图片已经写入的内容。"""
    first, second = tmp_path / "first.jpg", tmp_path / "second.jpg"
    for image in (first, second):
        Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    with readonly_file(first):
        with pytest.raises(LabelFileError, match="已更新 1 张图片"):
            save_annotation(first, "最新标注", otherData={"img_name_list": [first.name, second.name]})
        assert json.loads(first.with_suffix(".json").read_text(encoding="utf-8"))["shapes"][0]["label"] == "最新标注"
        assert read_image_json(first) is None
        assert read_image_json(second)["shapes"][0]["label"] == "最新标注"


def test_image_opened_without_write_sharing_reports_failure(tmp_path):
    """2026-10-09：真实读取占用禁止写入时保留失败，释放后仍保存内嵌标注。"""
    import ctypes
    from ctypes import wintypes

    image = tmp_path / "正在读取.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    original = image.read_bytes()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(image), 0x80000000, 1, None, 3, 128, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.WinError(ctypes.get_last_error())
    try:
        with pytest.raises(LabelFileError, match="Permission denied"):
            save_annotation(image, "保存后标注")
        assert read_image_json(image) is None
        assert image.read_bytes() == original
    finally:
        assert kernel.CloseHandle(handle)
    save_annotation(image, "保存后标注")
    assert read_image_json(image)["shapes"][0]["label"] == "保存后标注"
