import base64
import json
import struct
from pathlib import Path

import numpy as np
import pytest
from dlcv_core.image_json import ImageJsonError
from dlcv_core.image_json import read_image_json
from dlcv_core.image_json import write_image_json
from PIL import Image

from labelme import utils
from labelme.dlcv.label_file import LabelFile
from labelme.dlcv.label_file import LabelFileError
from labelme.dlcv.label_file import select_annotation_source


def _save_image(path):
    Image.new("RGB", (24, 16), (20, 80, 160)).save(path)


def _shape(label):
    return {
        "label": label,
        "points": [[1, 1], [12, 1], [12, 10], [1, 10]],
        "group_id": None,
        "description": None,
        "shape_type": "polygon",
        "flags": {},
        "mask": None,
    }


def test_save_writes_image_json_and_keeps_sidecar(tmp_path):
    image_path = tmp_path / "sample.png"
    sidecar_path = tmp_path / "sample.json"
    _save_image(image_path)

    label_file = LabelFile()
    label_file.save(
        filename=str(sidecar_path),
        shapes=[_shape("embedded")],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={},
        flags={"ok": True},
    )

    assert sidecar_path.exists()
    data = read_image_json(image_path)
    assert data["shapes"][0]["label"] == "embedded"
    loaded = LabelFile(str(image_path))
    assert loaded.shapes[0]["label"] == "embedded"
    assert loaded.flags == {"ok": True}


def test_renamed_embedded_image_uses_current_label_path(tmp_path):
    image_path = tmp_path / "current.png"
    _save_image(image_path)
    write_data = {
        "imagePath": "old.png",
        "shapes": [_shape("重命名")],
        "flags": {},
    }
    write_image_json(image_path, write_data)

    loaded = LabelFile(str(image_path))

    assert loaded.imagePath == image_path.name


def test_embedded_json_has_priority_over_external_json(tmp_path):
    image_path = tmp_path / "sample.jpg"
    sidecar_path = tmp_path / "sample.json"
    _save_image(image_path)
    label_file = LabelFile()
    label_file.save(
        filename=str(sidecar_path),
        shapes=[_shape("embedded")],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={},
        flags={},
    )
    sidecar_path.write_text(
        json.dumps(
            {
                "version": "5.0.1",
                "flags": {},
                "shapes": [_shape("sidecar")],
                "imagePath": image_path.name,
                "imageData": None,
                "imageHeight": 16,
                "imageWidth": 24,
            }
        ),
        encoding="utf-8",
    )

    loaded = LabelFile(str(sidecar_path))

    assert loaded.shapes[0]["label"] == "embedded"


def test_multi_image_annotation_is_written_to_each_image(tmp_path):
    first_image = tmp_path / "first.tif"
    second_image = tmp_path / "second.tif"
    sidecar_path = tmp_path / "pair.json"
    _save_image(first_image)
    _save_image(second_image)

    LabelFile().save(
        filename=str(sidecar_path),
        shapes=[_shape("pair")],
        imagePath=first_image.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={"img_name_list": [first_image.name, second_image.name]},
        flags={},
    )

    assert sidecar_path.exists()
    assert read_image_json(first_image)["shapes"][0]["label"] == "pair"
    assert read_image_json(second_image)["shapes"][0]["label"] == "pair"



def test_unsupported_image_format_keeps_external_json(tmp_path):
    image_path = tmp_path / "sample.gif"
    sidecar_path = tmp_path / "sample.json"
    _save_image(image_path)

    LabelFile().save(
        filename=str(sidecar_path),
        shapes=[_shape("sidecar")],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={},
        flags={},
    )

    assert sidecar_path.exists()



def test_file_tree_detects_embedded_annotation(tmp_path):
    from labelme.dlcv.file_tree_widget import _has_embedded_annotation

    image_path = tmp_path / "sample.webp"
    _save_image(image_path)
    assert not _has_embedded_annotation(image_path)
    LabelFile().save(
        filename=str(tmp_path / "sample.json"),
        shapes=[_shape("embedded")],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={},
        flags={},
    )
    assert _has_embedded_annotation(image_path)

def test_main_window_treats_embedded_json_as_label_file(tmp_path):
    from types import SimpleNamespace

    from labelme.dlcv.app import MainWindow

    image_path = tmp_path / "sample.bmp"
    sidecar_path = tmp_path / "sample.json"
    _save_image(image_path)
    LabelFile().save(
        filename=str(sidecar_path),
        shapes=[_shape("embedded")],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={},
        flags={},
    )
    window = SimpleNamespace(
        filename=str(image_path),
        getLabelFile=lambda: str(sidecar_path),
    )

    assert MainWindow.hasLabelFile(window)


def _save_label(
    label_file, image_path, filename=None, label="中文缺陷", other_data=None
):
    label_file.save(
        filename=str(filename or image_path.with_suffix(".json")),
        shapes=[_shape(label)], imagePath=image_path.name,
        imageHeight=16, imageWidth=24, imageData=None,
        otherData=other_data or {}, flags={},
    )


def test_manual_save_preserves_image_after_loading_embedded_json(tmp_path):
    from types import SimpleNamespace

    from labelme.app import MainWindow as BaseMainWindow

    image_path = tmp_path / "manual.png"
    _save_image(image_path)
    label_file = LabelFile()
    _save_label(label_file, image_path)
    loaded = LabelFile(str(image_path))
    targets = []
    window = SimpleNamespace(
        image=SimpleNamespace(isNull=lambda: False),
        labelFile=loaded, _saveFile=targets.append,
    )
    BaseMainWindow.saveFile(window)
    _save_label(loaded, image_path, filename=targets[0], label="修改后")
    with Image.open(image_path) as image:
        image.load()
        assert image.size == (24, 16)
    assert read_image_json(image_path)["shapes"][0]["label"] == "修改后"


def test_chinese_label_uses_utf8_for_embedded_and_external_json(tmp_path):
    for suffix in ["png", "gif"]:
        image_path = tmp_path / f"中文图片.{suffix}"
        _save_image(image_path)
        _save_label(LabelFile(), image_path)
        source = image_path if suffix == "png" else image_path.with_suffix(".json")
        loaded = LabelFile(str(source))
        assert loaded.shapes[0]["label"] == "中文缺陷"
        if suffix == "gif":
            data = json.loads(source.read_text(encoding="utf-8"))
            assert data["shapes"][0]["label"] == "中文缺陷"


def test_legacy_windows_encoding_remains_readable(tmp_path, monkeypatch):
    import locale
    image_path = tmp_path / "legacy.png"
    _save_image(image_path)
    sidecar = image_path.with_suffix(".json")
    data = {"imagePath": image_path.name, "shapes": [_shape("旧版中文")], "flags": {}}
    sidecar.write_bytes(json.dumps(data, ensure_ascii=False).encode("cp936"))
    monkeypatch.setattr(locale, "getencoding", lambda: "cp936")
    assert LabelFile(str(sidecar)).shapes[0]["label"] == "旧版中文"


def test_separate_output_directory_rebases_embedded_image_path(tmp_path):
    image_path = tmp_path / "sample.png"
    _save_image(image_path)
    output_dir = tmp_path / "labels"
    output_dir.mkdir()
    LabelFile().save(
        filename=str(output_dir / "sample.json"), shapes=[_shape("分目录")],
        imagePath="../sample.png", imageHeight=16, imageWidth=24,
        imageData=None, otherData={"img_name_list": [image_path.name]}, flags={},
    )
    assert read_image_json(image_path)["imagePath"] == image_path.name
    assert (output_dir / "sample.json").exists()


def test_bigtiff_keeps_readable_external_json(tmp_path):
    import numpy as np
    import tifffile

    image_path = tmp_path / "big.tif"
    tifffile.imwrite(image_path, np.zeros((16, 24), dtype=np.uint8), bigtiff=True)
    _save_label(LabelFile(), image_path)
    sidecar = image_path.with_suffix(".json")
    assert sidecar.is_file()
    assert select_annotation_source(image_path, sidecar) == sidecar
    assert LabelFile(str(sidecar)).shapes[0]["label"] == "中文缺陷"
    assert LabelFile(str(image_path)).shapes[0]["label"] == "中文缺陷"


def test_old_core_keeps_external_annotations(tmp_path, monkeypatch):
    from labelme.dlcv import label_file as module

    image_path = tmp_path / "old-core.png"
    _save_image(image_path)
    monkeypatch.setattr(module, "IMAGE_JSON_AVAILABLE", False)
    _save_label(LabelFile(), image_path)
    assert image_path.with_suffix(".json").exists()
    assert read_image_json(image_path) is None
    loaded = LabelFile(str(image_path.with_suffix(".json")))
    assert loaded.shapes[0]["label"] == "中文缺陷"


def test_mask_image_data_and_extra_shape_fields_round_trip(tmp_path):
    image_path = tmp_path / "semantic.png"
    _save_image(image_path)
    mask = np.zeros((16, 24), dtype=np.uint8)
    mask[2:6, 3:9] = 1
    shape = _shape("带掩码")
    shape["mask"] = utils.img_arr_to_b64(mask)
    shape["custom_score"] = 0.75
    image_data = image_path.read_bytes()

    LabelFile().save(
        filename=str(image_path.with_suffix(".json")),
        shapes=[shape],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=image_data,
        otherData={"custom_root": {"value": 1}},
        flags={"ok": True},
    )

    embedded = read_image_json(image_path)
    assert embedded["imageData"] == base64.b64encode(image_data).decode("utf-8")
    assert embedded["shapes"][0]["custom_score"] == 0.75
    loaded = LabelFile(str(image_path))
    assert loaded.imageData is None
    assert loaded.otherData["custom_root"] == {"value": 1}
    assert loaded.shapes[0]["other_data"]["custom_score"] == 0.75
    assert np.array_equal(loaded.shapes[0]["mask"], mask.astype(bool))


def test_failed_single_image_save_keeps_image_and_updates_external_backup(
    tmp_path, monkeypatch
):
    from labelme.dlcv import label_file as module

    image_path = tmp_path / "single.png"
    sidecar_path = image_path.with_suffix(".json")
    _save_image(image_path)
    _save_label(LabelFile(), image_path, label="旧标注")
    sidecar_data = {
        "imagePath": image_path.name,
        "shapes": [_shape("原外部标注")],
        "flags": {},
    }
    sidecar_path.write_text(
        json.dumps(sidecar_data, ensure_ascii=False), encoding="utf-8"
    )
    original_image = image_path.read_bytes()

    def fail_write(*_args, **_kwargs):
        raise OSError("模拟写入失败")

    monkeypatch.setattr(module, "write_image_json", fail_write)
    with pytest.raises(LabelFileError, match="模拟写入失败"):
        _save_label(
            LabelFile(),
            image_path,
            filename=sidecar_path,
            label="新标注",
        )

    assert image_path.read_bytes() == original_image
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["shapes"][0]["label"] == "新标注"
    assert read_image_json(image_path)["shapes"][0]["label"] == "旧标注"
    assert not [p for p in tmp_path.iterdir() if p.suffix in {".candidate", ".backup"}]


def test_failed_multi_image_save_keeps_successful_images_and_external_backup(
    tmp_path, monkeypatch
):
    from labelme.dlcv import label_file as module

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    sidecar_path = tmp_path / "pair.json"
    for image_path in [first, second]:
        _save_image(image_path)
    other_data = {"img_name_list": [first.name, second.name]}
    _save_label(LabelFile(), first, label="旧标注", other_data=other_data)
    sidecar_data = {
        "imagePath": first.name,
        "shapes": [_shape("原外部标注")],
        "flags": {},
        **other_data,
    }
    sidecar_path.write_text(
        json.dumps(sidecar_data, ensure_ascii=False), encoding="utf-8"
    )
    original_images = {path: path.read_bytes() for path in [first, second]}
    original_write = module.write_image_json

    def fail_second_image_write(image_path, *args, **kwargs):
        if Path(image_path) == second:
            raise OSError("模拟第二张图片写入失败")
        return original_write(image_path, *args, **kwargs)

    monkeypatch.setattr(module, "write_image_json", fail_second_image_write)
    with pytest.raises(LabelFileError, match="模拟第二张图片写入失败"):
        _save_label(
            LabelFile(),
            first,
            filename=sidecar_path,
            label="新标注",
            other_data=other_data,
        )

    assert second.read_bytes() == original_images[second]
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["shapes"][0]["label"] == "新标注"
    assert read_image_json(first)["shapes"][0]["label"] == "新标注"
    assert read_image_json(second)["shapes"][0]["label"] == "旧标注"
    assert not [p for p in tmp_path.iterdir() if p.suffix in {".candidate", ".backup"}]


def test_image_path_list_is_rebased_for_separate_output_directory(tmp_path):
    image_dir = tmp_path / "images"
    output_dir = tmp_path / "labels"
    image_dir.mkdir()
    output_dir.mkdir()
    first = image_dir / "first.png"
    second = image_dir / "second.png"
    for image_path in [first, second]:
        _save_image(image_path)

    LabelFile().save(
        filename=str(output_dir / "pair.json"),
        shapes=[_shape("分组")],
        imagePath="../images/first.png",
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={"image_path_list": [first.name, second.name]},
        flags={},
    )

    for image_path in [first, second]:
        embedded = read_image_json(image_path)
        assert embedded["imagePath"] == image_path.name
        assert embedded["image_path_list"] == [first.name, second.name]
    assert (output_dir / "pair.json").exists()


def test_corrupt_embedded_annotation_does_not_select_old_sidecar(tmp_path):
    image_path = tmp_path / "corrupt.png"
    sidecar_path = image_path.with_suffix(".json")
    _save_image(image_path)
    write_image_json(
        image_path,
        {
            "imagePath": image_path.name,
            "shapes": [_shape("图片内新标注")],
            "flags": {},
        },
    )
    sidecar_path.write_text(
        json.dumps(
            {
                "imagePath": image_path.name,
                "shapes": [_shape("外部旧标注")],
                "flags": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    image_data = bytearray(image_path.read_bytes())
    chunk_type = image_data.index(b"dlCV")
    chunk_length = struct.unpack(
        ">I", image_data[chunk_type - 4 : chunk_type]
    )[0]
    image_data[chunk_type + 4 + chunk_length - 1] ^= 0x01
    image_path.write_bytes(image_data)

    with pytest.raises(ImageJsonError, match="CRC"):
        select_annotation_source(image_path, sidecar_path)
    with pytest.raises(LabelFileError, match="CRC"):
        LabelFile(str(sidecar_path))


def _empty_save_window(image_path, sidecar_path, image_names):
    from types import SimpleNamespace

    errors = []
    window = SimpleNamespace(
        is_3d=False,
        is_2_5d=False,
        canvas=SimpleNamespace(shapes=[]),
        actions=SimpleNamespace(save=SimpleNamespace(setEnabled=lambda enabled: None)),
        labelList=[],
        flag_widget=SimpleNamespace(count=lambda: 0),
        filename=str(image_path),
        proj_manager=SimpleNamespace(
            get_img_name_list=lambda _filename: list(image_names)
        ),
        getLabelFile=lambda: str(sidecar_path),
        fix_shape=lambda _shape: None,
        tr=lambda text: text,
        errorMessage=lambda title, message: errors.append((title, message)),
    )
    return window, errors


def test_failed_single_image_clear_keeps_image_sidecar_and_temp_files_clean(
    tmp_path, monkeypatch
):
    from labelme.dlcv import label_file as module
    from labelme.dlcv.app import MainWindow

    image_path = tmp_path / "single.png"
    sidecar_path = image_path.with_suffix(".json")
    _save_image(image_path)
    _save_label(LabelFile(), image_path, label="图片内旧标注")
    sidecar_path.write_text(
        json.dumps(
            {
                "imagePath": image_path.name,
                "shapes": [_shape("外部旧标注")],
                "flags": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    original_image = image_path.read_bytes()
    original_sidecar = sidecar_path.read_bytes()

    original_unlink = module.Path.unlink

    def fail_sidecar_unlink(path, *args, **kwargs):
        if path == sidecar_path:
            raise OSError("模拟外部标注删除失败")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(module.Path, "unlink", fail_sidecar_unlink)
    window, errors = _empty_save_window(
        image_path, sidecar_path, [image_path.name]
    )

    assert MainWindow.saveLabels(window, str(sidecar_path)) is False
    assert window.dirty is True
    assert errors and "模拟外部标注删除失败" in errors[0][1]
    assert image_path.read_bytes() == original_image
    assert sidecar_path.read_bytes() == original_sidecar
    assert read_image_json(image_path)["shapes"][0]["label"] == "图片内旧标注"
    assert not [
        path
        for path in tmp_path.iterdir()
        if path.suffix in {".candidate", ".backup", ".tmp"}
    ]


def test_failed_multi_image_clear_rolls_back_images_and_keeps_sidecar(
    tmp_path, monkeypatch
):
    from labelme.dlcv import label_file as module
    from labelme.dlcv.app import MainWindow

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    sidecar_path = tmp_path / "pair.json"
    for image_path in [first, second]:
        _save_image(image_path)
    image_names = [first.name, second.name]
    _save_label(
        LabelFile(),
        first,
        label="图片内旧标注",
        other_data={"img_name_list": image_names},
    )
    sidecar_path.write_text(
        json.dumps(
            {
                "imagePath": first.name,
                "shapes": [_shape("外部旧标注")],
                "flags": {},
                "img_name_list": image_names,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    original_images = {path: path.read_bytes() for path in [first, second]}
    original_sidecar = sidecar_path.read_bytes()
    original_remove = module.remove_image_json

    def fail_second_image_clear(image_path, output_path=None):
        if Path(image_path) == second:
            raise OSError("模拟第二张图片清理失败")
        return original_remove(image_path, output_path=output_path)

    monkeypatch.setattr(module, "remove_image_json", fail_second_image_clear)
    window, errors = _empty_save_window(first, sidecar_path, image_names)

    assert MainWindow.saveLabels(window, str(sidecar_path)) is False
    assert window.dirty is True
    assert errors and "模拟第二张图片清理失败" in errors[0][1]
    assert {path: path.read_bytes() for path in [first, second]} == original_images
    assert sidecar_path.read_bytes() == original_sidecar
    assert read_image_json(first)["shapes"][0]["label"] == "图片内旧标注"
    assert read_image_json(second)["shapes"][0]["label"] == "图片内旧标注"
    assert not [
        path
        for path in tmp_path.iterdir()
        if path.suffix in {".candidate", ".backup", ".tmp"}
    ]


@pytest.mark.parametrize("existing_sidecar", [False, True])
def test_external_json_setting_never_disables_embedding_or_deletes_existing_json(
    tmp_path, existing_sidecar
):
    image = tmp_path / "sample.png"
    sidecar = image.with_suffix(".json")
    _save_image(image)
    if existing_sidecar:
        _save_label(LabelFile(), image, label="旧标注")
        original_sidecar = sidecar.read_bytes()
    LabelFile().save(
        str(sidecar), [_shape("新标注")], image.name, 16, 24,
        save_external_json=False,
    )
    assert read_image_json(image)["shapes"][0]["label"] == "新标注"
    assert sidecar.exists() == existing_sidecar
    if existing_sidecar:
        assert sidecar.read_bytes() == original_sidecar
        assert LabelFile(str(sidecar)).shapes[0]["label"] == "新标注"


def test_failed_embedding_writes_backup_even_when_external_saving_is_disabled(
    tmp_path, monkeypatch
):
    from labelme.dlcv import label_file as module

    image = tmp_path / "sample.png"
    _save_image(image)
    def fail_write(*args, **kwargs):
        raise OSError("图片不可写")
    monkeypatch.setattr(module, "write_image_json", fail_write)
    with pytest.raises(LabelFileError, match="最新标注已保存至外部 JSON"):
        LabelFile().save(
            str(image.with_suffix(".json")), [_shape("外部备份")], image.name,
            16, 24, save_external_json=False,
        )
    data = json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["shapes"][0]["label"] == "外部备份"


def test_missing_group_member_does_not_prevent_updating_existing_images(tmp_path):
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    for image in [first, last]:
        _save_image(image)
    names = [first.name, "missing.png", last.name]
    with pytest.raises(LabelFileError, match="missing.png"):
        _save_label(
            LabelFile(), first, label="最新标注", other_data={"img_name_list": names}
        )
    for image in [first, last]:
        data = read_image_json(image)
        assert data["imagePath"] == image.name
        assert data["shapes"][0]["label"] == "最新标注"
    assert json.loads(first.with_suffix(".json").read_text(encoding="utf-8"))["shapes"][0]["label"] == "最新标注"


def test_unsupported_group_member_keeps_supported_images_current(tmp_path):
    first = tmp_path / "first.png"
    unsupported = tmp_path / "second.gif"
    for image in [first, unsupported]:
        _save_image(image)
    _save_label(LabelFile(), first, label="旧标注")
    _save_label(
        LabelFile(), first, label="最新标注",
        other_data={"img_name_list": [first.name, unsupported.name]},
    )
    assert read_image_json(first)["shapes"][0]["label"] == "最新标注"
    assert LabelFile(str(first.with_suffix(".json"))).shapes[0]["label"] == "最新标注"


def test_sidecar_failure_keeps_successful_embedded_updates(tmp_path, monkeypatch):
    from labelme.dlcv import label_file as module

    image = tmp_path / "sample.png"
    _save_image(image)
    def fail_sidecar(*args, **kwargs):
        raise OSError("外部文件不可写")
    monkeypatch.setattr(module, "_write_sidecar", fail_sidecar)
    with pytest.raises(LabelFileError, match="外部文件不可写"):
        _save_label(LabelFile(), image, label="最新标注")
    assert read_image_json(image)["shapes"][0]["label"] == "最新标注"


@pytest.mark.parametrize("save_external_json", [False, True])
def test_auto_save_failure_preserves_dirty_edits_and_saves_backup(
    tmp_path, monkeypatch, save_external_json
):
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme.dlcv import label_file as module
    from labelme.dlcv.app import MainWindow

    image = tmp_path / "sample.png"
    sidecar = image.with_suffix(".json")
    _save_image(image)
    _save_label(LabelFile(), image, label="旧标注")
    window, errors = _empty_save_window(image, sidecar, [image.name])
    flag = SimpleNamespace(text=lambda: "最新标记", checkState=lambda: QtCore.Qt.Checked)
    window.flag_widget = SimpleNamespace(count=lambda: 1, item=lambda index: flag)
    window._config = {"store_data": False, "save_external_json": save_external_json}
    window.imagePath = str(image)
    window.imageData = None
    window.image = SimpleNamespace(height=lambda: 16, width=lambda: 24)
    window.otherData = {}
    original_label_file = LabelFile(str(image))
    window.labelFile = original_label_file
    def fail_write(*args, **kwargs):
        raise OSError("图片内写入失败")
    monkeypatch.setattr(module, "write_image_json", fail_write)

    assert MainWindow.saveLabels(window, str(sidecar)) is False
    assert window.dirty is True
    assert window.labelFile is original_label_file
    assert errors and "最新标注已保存至外部 JSON" in errors[0][1]
    assert json.loads(sidecar.read_text(encoding="utf-8"))["flags"] == {"最新标记": True}



def _folder_count_text(folder):
    from types import SimpleNamespace
    from labelme.dlcv.widget.label_count import LabelCountDock

    output = []
    panel = SimpleNamespace(
        parent=lambda: SimpleNamespace(lastOpenDir=str(folder)),
        label_count_text=SimpleNamespace(setText=output.append),
    )
    LabelCountDock.count_labels_in_dir(panel)
    return output[-1]


def test_folder_count_prefers_embedded_and_keeps_external_only_annotations(tmp_path):
    embedded = tmp_path / "embedded.png"
    external = tmp_path / "external.png"
    for image in [embedded, external]:
        _save_image(image)
    _save_label(LabelFile(), embedded, label="内嵌标签")
    for image, label in [(embedded, "旧外部标签"), (external, "外部标签")]:
        image.with_suffix(".json").write_text(
            json.dumps({"imagePath": image.name, "shapes": [_shape(label)]}),
            encoding="utf-8",
        )
    text = _folder_count_text(tmp_path)
    assert "共扫描 2 份标注" in text
    assert "内嵌标签: 1" in text
    assert "外部标签: 1" in text
    assert "旧外部标签" not in text
    assert "总数: 2" in text


def test_folder_count_reads_embedded_only_images(tmp_path):
    image = tmp_path / "embedded.png"
    _save_image(image)
    LabelFile().save(
        str(image.with_suffix(".json")), [_shape("内嵌标签")], image.name,
        16, 24, save_external_json=False,
    )
    text = _folder_count_text(tmp_path)
    assert "共扫描 1 份标注" in text
    assert "内嵌标签: 1" in text


def test_folder_count_counts_shared_images_and_sidecar_once(tmp_path):
    images = [tmp_path / "first.png", tmp_path / "second.png"]
    for image in images:
        _save_image(image)
    _save_label(
        LabelFile(), images[0], label="分组标签",
        other_data={"img_name_list": [image.name for image in images]},
    )
    text = _folder_count_text(tmp_path)
    assert "共扫描 1 份标注" in text
    assert "分组标签: 1" in text


def test_folder_count_keeps_external_mode_without_new_core(tmp_path, monkeypatch):
    from labelme.dlcv.widget import label_count as module

    sidecar = tmp_path / "sample.json"
    sidecar.write_text(json.dumps({"shapes": [_shape("外部标签")]}), encoding="utf-8")
    monkeypatch.setattr(module, "collect_annotation_paths", None)
    monkeypatch.setattr(module, "load_annotation", None)
    assert "外部标签: 1" in _folder_count_text(tmp_path)


def test_folder_count_reports_corrupt_embedded_image(tmp_path):
    (tmp_path / "corrupt.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    text = _folder_count_text(tmp_path)
    assert "读取文件夹标注失败" in text
    assert "未找到任何标注" not in text



def test_folder_count_keeps_independent_sidecar_after_renaming_2d_image(tmp_path):
    from shutil import copy2
    from dlcv_core.image_json import remove_image_json

    original = tmp_path / "original.png"
    renamed = tmp_path / "renamed.png"
    _save_image(original)
    _save_label(
        LabelFile(), original, label="内嵌副本",
        other_data={"img_name_list": [original.name]},
    )
    copy2(original, renamed)
    remove_image_json(original)
    original.with_suffix(".json").write_text(
        json.dumps({"imagePath": original.name, "shapes": [_shape("独立外部标注")]}),
        encoding="utf-8",
    )
    text = _folder_count_text(tmp_path)
    assert "共扫描 2 份标注" in text
    assert "内嵌副本: 1" in text
    assert "独立外部标注: 1" in text


@pytest.mark.parametrize("custom_name", ["sample.json", "export.json"])
def test_manual_save_keeps_external_output_path(tmp_path, custom_name):
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme.app import MainWindow as BaseMainWindow
    from labelme.dlcv.app import MainWindow

    image_path = tmp_path / "sample.png"
    sidecar_path = tmp_path / "labels" / custom_name
    _save_image(image_path)
    window, errors = _empty_save_window(image_path, sidecar_path, [image_path.name])
    current_flag = {"label": "第一次"}
    flag = SimpleNamespace(
        text=lambda: current_flag["label"], checkState=lambda: QtCore.Qt.Checked
    )
    window.flag_widget = SimpleNamespace(count=lambda: 1, item=lambda index: flag)
    window._config = {"store_data": False, "save_external_json": True}
    window.imagePath = str(image_path)
    window.imageData = None
    window.image = SimpleNamespace(height=lambda: 16, width=lambda: 24, isNull=lambda: False)
    window.otherData = {}
    window.output_dir = str(sidecar_path.parent)
    window.getLabelFile = lambda: str(image_path.with_suffix(".json"))
    window.fileListWidget = SimpleNamespace(findItems=lambda *args: [])
    window._saveFile = lambda filename: MainWindow.saveLabels(window, filename)

    assert MainWindow.saveLabels(window, str(sidecar_path))
    current_flag["label"] = "第二次"
    BaseMainWindow.saveFile(window)

    assert not errors
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["flags"] == {"第二次": True}
    assert read_image_json(image_path)["flags"] == {"第二次": True}
    assert not image_path.with_suffix(".json").exists()


def test_label_file_keeps_sidecar_after_embedded_reload(tmp_path):
    image = tmp_path / "sample.png"
    output = tmp_path / "labels" / "custom.json"
    _save_image(image)
    label_file = LabelFile()
    label_file.save(
        filename=str(output), shapes=[_shape("第一次")], imagePath="../sample.png",
        imageHeight=16, imageWidth=24, flags={},
    )
    label_file.load(label_file.filename)
    label_file.save(
        filename=label_file.filename, shapes=[_shape("第二次")], imagePath=label_file.imagePath,
        imageHeight=16, imageWidth=24, flags={},
    )
    assert json.loads(output.read_text(encoding="utf-8"))["shapes"][0]["label"] == "第二次"
    assert read_image_json(image)["shapes"][0]["label"] == "第二次"
    assert not image.with_suffix(".json").exists()


def test_save_and_clear_use_memory_buffers_for_long_names(tmp_path, monkeypatch):
    import tempfile
    from labelme.dlcv.label_file import remove_image_annotations

    image = tmp_path / ("a" * 240 + ".png")
    _save_image(image)

    def reject_disk_temporary_file(*args, **kwargs):
        raise AssertionError("不应创建磁盘临时文件")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", reject_disk_temporary_file)
    _save_label(LabelFile(), image)
    assert read_image_json(image)["shapes"][0]["label"] == "中文缺陷"
    assert json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))["imagePath"] == image.name
    assert set(tmp_path.iterdir()) == {image, image.with_suffix(".json")}
    remove_image_annotations([image], image.with_suffix(".json"))
    assert read_image_json(image) is None
    assert list(tmp_path.iterdir()) == [image]


@pytest.mark.parametrize("existing", [False, True])
def test_partial_sidecar_write_restores_previous_file(tmp_path, monkeypatch, existing):
    from labelme.dlcv.label_file import _write_sidecar

    sidecar = tmp_path / "sample.json"
    original = b'{"flags":{"old":true}}'
    if existing:
        sidecar.write_bytes(original)
    original_open = Path.open
    failed = False

    class FailedWriter:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, data):
            self.file.write(data[:8])
            raise OSError("模拟写入中断")

    def fail_first_write(path, mode="r", *args, **kwargs):
        nonlocal failed
        file = original_open(path, mode, *args, **kwargs)
        if path == sidecar and mode == "wb" and not failed:
            failed = True
            return FailedWriter(file)
        return file

    monkeypatch.setattr(Path, "open", fail_first_write)
    with pytest.raises(OSError, match="模拟写入中断"):
        _write_sidecar(sidecar, {"flags": {"latest": True}})
    if existing:
        assert sidecar.read_bytes() == original
    else:
        assert not sidecar.exists()
