"""使用真实只读图片检查外部标注保存，不修改图片属性。"""

import json
import os
import stat
from contextlib import contextmanager

import pytest
from PIL import Image
from dlcv_core.image_json import read_image_json

from labelme.dlcv.label_file import LabelFile, LabelFileError, select_annotation_source

pytestmark = pytest.mark.skipif(os.name != "nt", reason="使用 Windows 只读文件属性")


def _shape(label):
    return {"label": label, "points": [[1, 1], [12, 1], [12, 10], [1, 10]],
            "shape_type": "polygon", "flags": {}, "group_id": None, "mask": None}


def _save(image, label, **kwargs):
    label_file = LabelFile()
    label_file.save(str(image.with_suffix(".json")), [_shape(label)], image.name,
                    16, 24, **kwargs)
    return label_file


@contextmanager
def _readonly(path):
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
    image = tmp_path / ("只读图片" + extension)
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    original = image.read_bytes()
    with _readonly(image):
        for label in ("首次标注", "最新标注"):
            saved = _save(image, label, save_external_json=save_external_json)
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
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    _save(image, "原标注")
    original = image.read_bytes()
    with _readonly(image):
        saved = _save(image, "原标注")
        assert saved.filename == str(image)
        assert image.read_bytes() == original
        assert LabelFile(str(image)).shapes[0]["label"] == "原标注"


def test_readonly_stale_embedded_annotation_still_reports_failure(tmp_path):
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    _save(image, "旧标注")
    original = image.read_bytes()
    with _readonly(image), pytest.raises(LabelFileError, match="最新标注已保存至外部 JSON"):
        _save(image, "最新标注")
    assert image.read_bytes() == original
    assert read_image_json(image)["shapes"][0]["label"] == "旧标注"
    assert json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))["shapes"][0]["label"] == "最新标注"


def test_readonly_sidecar_write_failure_is_not_treated_as_saved(tmp_path):
    image = tmp_path / "sample.jpg"
    Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    sidecar = image.with_suffix(".json")
    sidecar.write_text('{"shapes": []}', encoding="utf-8")
    original = sidecar.read_bytes()
    with _readonly(image), _readonly(sidecar), pytest.raises(LabelFileError):
        _save(image, "最新标注")
    assert sidecar.read_bytes() == original
    assert read_image_json(image) is None


def test_group_with_readonly_unembedded_image_saves_each_annotation(tmp_path):
    first, second = tmp_path / "first.jpg", tmp_path / "second.jpg"
    for image in (first, second):
        Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    with _readonly(first):
        _save(first, "最新标注", otherData={"img_name_list": [first.name, second.name]})
        assert LabelFile(str(first)).shapes[0]["label"] == "最新标注"
        assert read_image_json(first) is None
        assert read_image_json(second)["shapes"][0]["label"] == "最新标注"


def test_image_opened_without_write_sharing_saves_external_json(tmp_path):
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
        _save(image, "保存后标注")
        assert LabelFile(str(image)).shapes[0]["label"] == "保存后标注"
        assert read_image_json(image) is None
        assert image.read_bytes() == original
    finally:
        assert kernel.CloseHandle(handle)
