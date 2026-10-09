"""2026-10-09：只读或读取占用触发图片写入拒绝，外部标注已保存仍报错。
以下用真实文件属性和系统文件句柄检查保存、重开及数据保留，防止误报再次出现。
"""

import json
import os
import stat
from contextlib import contextmanager

import pytest
from PIL import Image
from dlcv_core.image_json import read_image_json

from labelme.dlcv.label_file import LabelFile, LabelFileError, select_annotation_source

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
def test_readonly_image_saves_and_reopens_latest_external_annotations(
    tmp_path, extension, save_external_json, caplog
):
    """2026-10-09：只读图片外部保存曾误报；用连续保存和重开确认最新标注可读。"""
    image = tmp_path / ("只读图片" + extension)
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    original = image.read_bytes()
    with readonly_file(image):
        for label in ("首次标注", "最新标注"):
            saved = save_annotation(image, label, save_external_json=save_external_json)
            sidecar = image.with_suffix(".json")
            assert saved.filename == str(sidecar)
            assert select_annotation_source(image, sidecar) == sidecar
            assert LabelFile(str(image)).shapes[0]["label"] == label
            assert LabelFile(str(sidecar)).shapes[0]["label"] == label
            assert json.loads(sidecar.read_text(encoding="utf-8"))["shapes"][0]["label"] == label
            assert image.read_bytes() == original
            assert image.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
            assert read_image_json(image) is None
    assert "外部 JSON" in caplog.text


def test_readonly_existing_embedded_annotation_can_save_without_changes(tmp_path):
    """2026-10-09：只读图片重复写入被拒绝；确认已有相同内嵌数据无需重写。"""
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    save_annotation(image, "原标注")
    original = image.read_bytes()
    with readonly_file(image):
        saved = save_annotation(image, "原标注")
        assert saved.filename == str(image)
        assert image.read_bytes() == original
        assert LabelFile(str(image)).shapes[0]["label"] == "原标注"


def test_readonly_stale_embedded_annotation_still_reports_failure(tmp_path):
    """2026-10-09：处理写入拒绝时须保留真实失败；防止旧内嵌数据被误判为最新。"""
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
    """2026-10-09：外部保存是判定依据；文件也不可写时必须继续报告失败。"""
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    sidecar = image.with_suffix(".json")
    sidecar.write_text('{"shapes": []}', encoding="utf-8")
    original = sidecar.read_bytes()
    with readonly_file(image), readonly_file(sidecar), pytest.raises(LabelFileError):
        save_annotation(image, "最新标注")
    assert sidecar.read_bytes() == original
    assert read_image_json(image) is None


def test_group_with_readonly_unembedded_image_saves_each_annotation(tmp_path):
    """2026-10-09：组保存共用受限写入流程；确认可写图片与外部标注均保存最新内容。"""
    first, second = tmp_path / "first.jpg", tmp_path / "second.jpg"
    for image in (first, second):
        Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    with readonly_file(first):
        save_annotation(first, "最新标注", otherData={"img_name_list": [first.name, second.name]})
        assert LabelFile(str(first)).shapes[0]["label"] == "最新标注"
        assert read_image_json(first) is None
        assert read_image_json(second)["shapes"][0]["label"] == "最新标注"


def test_image_opened_without_write_sharing_saves_external_json(tmp_path):
    """2026-10-09：读取占用可触发同类拒绝；用真实系统句柄确认外部标注仍可保存。"""
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
        save_annotation(image, "保存后标注")
        assert LabelFile(str(image)).shapes[0]["label"] == "保存后标注"
        assert read_image_json(image) is None
        assert image.read_bytes() == original
    finally:
        assert kernel.CloseHandle(handle)
