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


def save_image(path):
    Image.new("RGB", (24, 16), (20, 80, 160)).save(path)


def annotation_shape(label):
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
    save_image(image_path)

    label_file = LabelFile()
    label_file.save(
        filename=str(sidecar_path),
        shapes=[annotation_shape("embedded")],
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


def test_renamed_embedded_image_does_not_restore_missing_external_json(tmp_path):
    image_path = tmp_path / "current.png"
    save_image(image_path)
    write_image_json(image_path, {"imagePath": "old.png", "shapes": [annotation_shape("历史标注")], "flags": {}})
    before = image_path.read_bytes()
    assert select_annotation_source(image_path, image_path.with_suffix(".json")) is None
    with pytest.raises(LabelFileError):
        LabelFile(str(image_path))
    assert read_image_json(image_path)["shapes"][0]["label"] == "历史标注"
    assert image_path.read_bytes() == before


def test_external_json_has_priority_over_embedded_json(tmp_path):
    image_path = tmp_path / "sample.jpg"
    sidecar_path = tmp_path / "sample.json"
    save_image(image_path)
    label_file = LabelFile()
    label_file.save(
        filename=str(sidecar_path),
        shapes=[annotation_shape("embedded")],
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
                "shapes": [{**annotation_shape("sidecar"), "points": [[4, 3], [18, 3], [18, 12], [4, 12]]}],
                "imagePath": image_path.name,
                "imageData": None,
                "imageHeight": 16,
                "imageWidth": 24,
            }
        ),
        encoding="utf-8",
    )

    loaded = LabelFile(str(sidecar_path))

    assert loaded.shapes[0]["label"] == "sidecar"
    assert loaded.shapes[0]["points"] == [[4, 3], [18, 3], [18, 12], [4, 12]]
    assert LabelFile(str(image_path)).shapes[0]["label"] == "sidecar"
    assert read_image_json(image_path)["shapes"][0]["label"] == "embedded"


def test_multi_image_annotation_is_written_to_each_image(tmp_path):
    first_image = tmp_path / "first.tif"
    second_image = tmp_path / "second.tif"
    sidecar_path = tmp_path / "pair.json"
    save_image(first_image)
    save_image(second_image)

    LabelFile().save(
        filename=str(sidecar_path),
        shapes=[annotation_shape("pair")],
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
    save_image(image_path)

    LabelFile().save(
        filename=str(sidecar_path),
        shapes=[annotation_shape("sidecar")],
        imagePath=image_path.name,
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={},
        flags={},
    )

    assert sidecar_path.exists()



def test_file_tree_checks_external_json_only(qapp, tmp_path):
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme.dlcv.file_tree_widget import _FileTreeWidget
    from labelme.dlcv.store import STORE

    image_path = tmp_path / "sample.webp"
    save_image(image_path)
    sidecar_path = image_path.with_suffix(".json")
    write_image_json(image_path, {"imagePath": image_path.name, "shapes": [annotation_shape("内嵌")], "flags": {}})
    try:
        previous = STORE.main_window
    except AssertionError:
        previous = None
    STORE.register_main_window(SimpleNamespace(proj_manager=SimpleNamespace(
        get_json_path=lambda path: str(Path(path).with_suffix(".json")))))
    tree = _FileTreeWidget()
    try:
        tree.set_root_dir(str(tmp_path))
        item = tree._file_items[image_path.as_posix()]
        assert item.checkState(0) == QtCore.Qt.Unchecked
        save_label(LabelFile(), image_path, label="外部")
        tree.update_state()
        assert item.checkState(0) == QtCore.Qt.Checked
        sidecar_path.unlink()
        tree.update_state()
        assert item.checkState(0) == QtCore.Qt.Unchecked
    finally:
        tree.close()
        tree.deleteLater()
        qapp.processEvents()
        STORE.register_main_window(previous)

def test_main_window_requires_external_json_for_label_file(tmp_path):
    from types import SimpleNamespace

    from labelme.dlcv.app import MainWindow

    image_path = tmp_path / "sample.bmp"
    sidecar_path = tmp_path / "sample.json"
    save_image(image_path)
    LabelFile().save(
        filename=str(sidecar_path),
        shapes=[annotation_shape("embedded")],
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
    sidecar_path.unlink()
    assert not MainWindow.hasLabelFile(window)


def save_label(
    label_file, image_path, filename=None, label="中文缺陷", other_data=None
):
    label_file.save(
        filename=str(filename or image_path.with_suffix(".json")),
        shapes=[annotation_shape(label)], imagePath=image_path.name,
        imageHeight=16, imageWidth=24, imageData=None,
        otherData=other_data or {}, flags={},
    )


def test_manual_save_preserves_image_after_loading_embedded_json(tmp_path):
    from types import SimpleNamespace

    from labelme.app import MainWindow as BaseMainWindow

    image_path = tmp_path / "manual.png"
    save_image(image_path)
    label_file = LabelFile()
    save_label(label_file, image_path)
    loaded = LabelFile(str(image_path))
    targets = []
    window = SimpleNamespace(
        image=SimpleNamespace(isNull=lambda: False),
        labelFile=loaded, _saveFile=targets.append,
    )
    BaseMainWindow.saveFile(window)
    save_label(loaded, image_path, filename=targets[0], label="修改后")
    with Image.open(image_path) as image:
        image.load()
        assert image.size == (24, 16)
    assert read_image_json(image_path)["shapes"][0]["label"] == "修改后"


def test_chinese_label_uses_utf8_for_embedded_and_external_json(tmp_path):
    for suffix in ["png", "gif"]:
        image_path = tmp_path / f"中文图片.{suffix}"
        save_image(image_path)
        save_label(LabelFile(), image_path)
        source = image_path if suffix == "png" else image_path.with_suffix(".json")
        loaded = LabelFile(str(source))
        assert loaded.shapes[0]["label"] == "中文缺陷"
        if suffix == "gif":
            data = json.loads(source.read_text(encoding="utf-8"))
            assert data["shapes"][0]["label"] == "中文缺陷"


def test_legacy_windows_encoding_remains_readable(tmp_path, monkeypatch):
    import locale
    image_path = tmp_path / "legacy.png"
    save_image(image_path)
    sidecar = image_path.with_suffix(".json")
    data = {"imagePath": image_path.name, "shapes": [annotation_shape("旧版中文")], "flags": {}}
    sidecar.write_bytes(json.dumps(data, ensure_ascii=False).encode("cp936"))
    monkeypatch.setattr(locale, "getencoding", lambda: "cp936")
    assert LabelFile(str(sidecar)).shapes[0]["label"] == "旧版中文"


def test_separate_output_directory_rebases_embedded_image_path(tmp_path):
    image_path = tmp_path / "sample.png"
    save_image(image_path)
    output_dir = tmp_path / "labels"
    output_dir.mkdir()
    LabelFile().save(
        filename=str(output_dir / "sample.json"), shapes=[annotation_shape("分目录")],
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
    save_label(LabelFile(), image_path)
    sidecar = image_path.with_suffix(".json")
    assert sidecar.is_file()
    assert select_annotation_source(image_path, sidecar) == sidecar
    assert LabelFile(str(sidecar)).shapes[0]["label"] == "中文缺陷"
    assert LabelFile(str(image_path)).shapes[0]["label"] == "中文缺陷"


def test_mask_image_data_and_extra_shape_fields_round_trip(tmp_path):
    image_path = tmp_path / "semantic.png"
    save_image(image_path)
    mask = np.zeros((16, 24), dtype=np.uint8)
    mask[2:6, 3:9] = 1
    shape = annotation_shape("带掩码")
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
    save_image(image_path)
    save_label(LabelFile(), image_path, label="旧标注")
    sidecar_data = {
        "imagePath": image_path.name,
        "shapes": [annotation_shape("原外部标注")],
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
        save_label(
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
        save_image(image_path)
    other_data = {"img_name_list": [first.name, second.name]}
    save_label(LabelFile(), first, label="旧标注", other_data=other_data)
    sidecar_data = {
        "imagePath": first.name,
        "shapes": [annotation_shape("原外部标注")],
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
        save_label(
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
        save_image(image_path)

    LabelFile().save(
        filename=str(output_dir / "pair.json"),
        shapes=[annotation_shape("分组")],
        imagePath="../images/first.png",
        imageHeight=16,
        imageWidth=24,
        imageData=None,
        otherData={"image_path_list": ["../images/first.png", "../images/second.png"]},
        flags={},
    )

    for image_path in [first, second]:
        embedded = read_image_json(image_path)
        assert embedded["imagePath"] == image_path.name
        assert embedded["image_path_list"] == [first.name, second.name]
    external = json.loads((output_dir / "pair.json").read_text(encoding="utf-8"))
    assert [(output_dir / name).resolve() for name in external["image_path_list"]] == [first, second]


def test_corrupt_embedded_annotation_does_not_replace_external_json(tmp_path):
    image_path = tmp_path / "corrupt.png"
    save_image(image_path)
    save_label(LabelFile(), image_path, label="外部标注")
    sidecar_path = image_path.with_suffix(".json")
    image_data = bytearray(image_path.read_bytes())
    chunk_type = image_data.index(b"dlCV")
    chunk_length = struct.unpack(">I", image_data[chunk_type - 4:chunk_type])[0]
    image_data[chunk_type + 4 + chunk_length - 1] ^= 1
    image_path.write_bytes(image_data)
    assert select_annotation_source(image_path, sidecar_path) == sidecar_path
    for source in (image_path, sidecar_path):
        assert LabelFile(str(source)).shapes[0]["label"] == "外部标注"
    with pytest.raises(ImageJsonError, match="CRC"):
        read_image_json(image_path)


def empty_save_window(image_path, sidecar_path, image_names):
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
        otherData={},
        proj_manager=SimpleNamespace(
            get_img_name_list=lambda _filename: list(image_names)
        ),
        getLabelFile=lambda: str(sidecar_path),
        fix_shape=lambda shape: None,
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
    save_image(image_path)
    save_label(LabelFile(), image_path, label="图片内旧标注")
    sidecar_path.write_text(
        json.dumps(
            {
                "imagePath": image_path.name,
                "shapes": [annotation_shape("外部旧标注")],
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
    window, errors = empty_save_window(
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
        save_image(image_path)
    image_names = [first.name, second.name]
    save_label(
        LabelFile(),
        first,
        label="图片内旧标注",
        other_data={"img_name_list": image_names},
    )
    sidecar_path.write_text(
        json.dumps(
            {
                "imagePath": first.name,
                "shapes": [annotation_shape("外部旧标注")],
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
    window, errors = empty_save_window(first, sidecar_path, image_names)

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


def test_group_sidecar_clear_failure_restores_all_originals(tmp_path, monkeypatch):
    from labelme.dlcv import label_file as module

    images = [tmp_path / "first.png", tmp_path / "second.png"]
    for image in images:
        save_image(image)
        save_label(LabelFile(), image, label="原标注")
    sidecars = [image.with_suffix(".json") for image in images]
    originals = {path: path.read_bytes() for path in [*images, *sidecars]}
    original_unlink = module.Path.unlink

    def fail_second_sidecar(path, *args, **kwargs):
        if path == sidecars[1]:
            raise PermissionError("第二张图片的外部标注不可删除")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(module.Path, "unlink", fail_second_sidecar)
    with pytest.raises(LabelFileError, match="第二张图片"):
        module.remove_image_annotations(images, sidecars[0])
    assert {path: path.read_bytes() for path in originals} == originals


@pytest.mark.parametrize("existing_sidecar", [False, True])
def test_old_disabled_setting_still_updates_external_and_embedded_json(tmp_path, existing_sidecar):
    image = tmp_path / "sample.png"
    sidecar = image.with_suffix(".json")
    save_image(image)
    if existing_sidecar:
        save_label(LabelFile(), image, label="旧标注")
    label_file = LabelFile()
    label_file.save(str(sidecar), [annotation_shape("新标注")], image.name, 16, 24, save_external_json=False)
    external = json.loads(sidecar.read_text(encoding="utf-8"))
    embedded = read_image_json(image)
    assert external["shapes"] == embedded["shapes"] == [annotation_shape("新标注")]
    assert (external["imageWidth"], external["imageHeight"]) == (24, 16)
    assert (embedded["imageWidth"], embedded["imageHeight"]) == (24, 16)
    assert label_file.filename == str(sidecar)
    assert LabelFile(str(sidecar)).shapes[0]["label"] == "新标注"


def test_failed_embedding_writes_backup_even_when_external_saving_is_disabled(
    tmp_path, monkeypatch
):
    from labelme.dlcv import label_file as module

    image = tmp_path / "sample.png"
    save_image(image)
    def fail_write(*args, **kwargs):
        raise OSError("图片不可写")
    monkeypatch.setattr(module, "write_image_json", fail_write)
    with pytest.raises(LabelFileError, match="最新标注已保存至外部 JSON"):
        LabelFile().save(
            str(image.with_suffix(".json")), [annotation_shape("外部备份")], image.name,
            16, 24, save_external_json=False,
        )
    data = json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["shapes"][0]["label"] == "外部备份"


def test_missing_group_member_does_not_prevent_updating_existing_images(tmp_path):
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    for image in [first, last]:
        save_image(image)
    names = [first.name, "missing.png", last.name]
    with pytest.raises(LabelFileError, match="missing.png"):
        save_label(
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
        save_image(image)
    save_label(LabelFile(), first, label="旧标注")
    save_label(
        LabelFile(), first, label="最新标注",
        other_data={"img_name_list": [first.name, unsupported.name]},
    )
    assert read_image_json(first)["shapes"][0]["label"] == "最新标注"
    assert LabelFile(str(first.with_suffix(".json"))).shapes[0]["label"] == "最新标注"


def test_sidecar_failure_keeps_successful_embedded_updates(tmp_path, monkeypatch):
    from labelme.dlcv import label_file as module

    image = tmp_path / "sample.png"
    save_image(image)
    def fail_sidecar(*args, **kwargs):
        raise OSError("外部文件不可写")
    monkeypatch.setattr(module, "_write_sidecar", fail_sidecar)
    with pytest.raises(LabelFileError, match="外部文件不可写"):
        save_label(LabelFile(), image, label="最新标注")
    assert read_image_json(image)["shapes"][0]["label"] == "最新标注"


@pytest.mark.parametrize("save_external_json", [False, True])
def test_auto_save_failure_preserves_dirty_edits_and_saves_backup(
    tmp_path, monkeypatch, save_external_json, caplog
):
    """保存失败保留编辑，日志包含原始写入异常。"""
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme.dlcv import label_file as module
    from labelme.dlcv.app import MainWindow

    image = tmp_path / "sample.png"
    sidecar = image.with_suffix(".json")
    save_image(image)
    save_label(LabelFile(), image, label="旧标注")
    window, errors = empty_save_window(image, sidecar, [image.name])
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
    assert "保存标注失败" in caplog.text
    assert "Traceback" in caplog.text
    assert str(sidecar) in caplog.text
    assert json.loads(sidecar.read_text(encoding="utf-8"))["flags"] == {"最新标记": True}



@pytest.mark.parametrize("save_external_json", [False, True])
def test_real_readonly_jpeg_failure_writes_complete_traceback(tmp_path, save_external_json):
    """真实只读 JPG 保存失败，文件日志必须追溯到最初的图片写入调用。"""
    import logging
    import os
    import stat
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme.dlcv.app import MainWindow
    from labelme.logger import logger

    if os.name != "nt":
        pytest.skip("使用 Windows 只读属性")
    image = tmp_path / "只读图片.jpg"
    sidecar = image.with_suffix(".json")
    save_image(image)
    original = image.read_bytes()
    original_mode = image.stat().st_mode
    window, errors = empty_save_window(image, sidecar, [image.name])
    flag = SimpleNamespace(text=lambda: "最新标记", checkState=lambda: QtCore.Qt.Checked)
    window.flag_widget = SimpleNamespace(count=lambda: 1, item=lambda index: flag)
    window._config = {"store_data": False, "save_external_json": save_external_json}
    window.imagePath = str(image)
    window.imageData = None
    window.image = SimpleNamespace(height=lambda: 16, width=lambda: 24)
    window.dirty = True
    window.labelFile = None
    handler = next(h for h in logger.handlers if isinstance(h, logging.FileHandler))
    log_path = Path(handler.baseFilename)
    offset = log_path.stat().st_size
    image.chmod(stat.S_IREAD)
    try:
        assert MainWindow.saveLabels(window, str(sidecar)) is False
        assert window.dirty is True and errors
        assert image.read_bytes() == original
    finally:
        image.chmod(original_mode)
    handler.flush()
    text = log_path.read_bytes()[offset:].decode("utf-8")
    assert "保存标注失败" in text and "Traceback (most recent call last)" in text
    assert "PermissionError" in text and "image_json.py" in text
    assert "_write_image_buffer" in text and str(image) in text
    assert "line " in text and "The above exception was the direct cause" in text


def folder_count_text(folder):
    from types import SimpleNamespace
    from labelme.dlcv.widget.label_count import LabelCountDock

    output = []
    panel = SimpleNamespace(
        parent=lambda: SimpleNamespace(lastOpenDir=str(folder)),
        label_count_text=SimpleNamespace(setText=output.append),
    )
    LabelCountDock.count_labels_in_dir(panel)
    return output[-1]


def test_folder_count_prefers_external_and_keeps_external_only_annotations(tmp_path):
    embedded = tmp_path / "embedded.png"
    external = tmp_path / "external.png"
    for image in [embedded, external]:
        save_image(image)
    save_label(LabelFile(), embedded, label="内嵌标签")
    for image, label in [(embedded, "旧外部标签"), (external, "外部标签")]:
        image.with_suffix(".json").write_text(
            json.dumps({"imagePath": image.name, "shapes": [annotation_shape(label)]}),
            encoding="utf-8",
        )
    text = folder_count_text(tmp_path)
    assert "共扫描 2 份标注" in text
    assert "旧外部标签: 1" in text
    assert "外部标签: 1" in text
    assert "内嵌标签" not in text
    assert "总数: 2" in text


def test_folder_count_ignores_embedded_only_images(tmp_path):
    image = tmp_path / "embedded.png"
    save_image(image)
    write_image_json(image, {"imagePath": image.name, "shapes": [annotation_shape("内嵌标签")], "flags": {}})
    text = folder_count_text(tmp_path)
    assert "未找到任何标注" in text
    assert "内嵌标签" not in text
    assert read_image_json(image)["shapes"][0]["label"] == "内嵌标签"


def test_folder_count_counts_shared_images_and_sidecar_once(tmp_path):
    images = [tmp_path / "first.png", tmp_path / "second.png"]
    for image in images:
        save_image(image)
    save_label(
        LabelFile(), images[0], label="分组标签",
        other_data={"img_name_list": [image.name for image in images]},
    )
    text = folder_count_text(tmp_path)
    assert "共扫描 1 份标注" in text
    assert "分组标签: 1" in text


def test_folder_count_reports_corrupt_external_json_path(tmp_path):
    image = tmp_path / "corrupt.png"
    save_image(image)
    save_label(LabelFile(), image, label="旧内嵌")
    sidecar = image.with_suffix(".json")
    sidecar.write_text("{", encoding="utf-8")
    text = folder_count_text(tmp_path)
    assert "读取失败" in text
    assert str(sidecar) in text
    assert "旧内嵌" not in text



def test_folder_count_keeps_independent_sidecar_after_renaming_2d_image(tmp_path):
    from shutil import copy2
    from dlcv_core.image_json import remove_image_json

    original = tmp_path / "original.png"
    renamed = tmp_path / "renamed.png"
    save_image(original)
    save_label(
        LabelFile(), original, label="内嵌副本",
        other_data={"img_name_list": [original.name]},
    )
    copy2(original, renamed)
    remove_image_json(original)
    original.with_suffix(".json").write_text(
        json.dumps({"imagePath": original.name, "shapes": [annotation_shape("独立外部标注")]}),
        encoding="utf-8",
    )
    text = folder_count_text(tmp_path)
    assert "共扫描 1 份标注" in text
    assert "内嵌副本" not in text
    assert "独立外部标注: 1" in text


@pytest.mark.parametrize("custom_name", ["sample.json", "export.json"])
def test_manual_save_keeps_external_output_path(tmp_path, custom_name):
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme.app import MainWindow as BaseMainWindow
    from labelme.dlcv.app import MainWindow

    image_path = tmp_path / "sample.png"
    sidecar_path = tmp_path / "labels" / custom_name
    save_image(image_path)
    window, errors = empty_save_window(image_path, sidecar_path, [image_path.name])
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
    window.fileListWidget = SimpleNamespace(findItems=lambda *args: [], update_state=lambda: None)
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
    save_image(image)
    label_file = LabelFile()
    label_file.save(
        filename=str(output), shapes=[annotation_shape("第一次")], imagePath="../sample.png",
        imageHeight=16, imageWidth=24, flags={},
    )
    label_file.load(label_file.filename)
    label_file.save(
        filename=label_file.filename, shapes=[annotation_shape("第二次")], imagePath=label_file.imagePath,
        imageHeight=16, imageWidth=24, flags={},
    )
    assert json.loads(output.read_text(encoding="utf-8"))["shapes"][0]["label"] == "第二次"
    assert read_image_json(image)["shapes"][0]["label"] == "第二次"
    assert not image.with_suffix(".json").exists()


def test_save_and_clear_use_memory_buffers_for_long_names(tmp_path, monkeypatch):
    import tempfile
    from labelme.dlcv.label_file import remove_image_annotations

    image = tmp_path / ("a" * 240 + ".png")
    save_image(image)

    def reject_disk_temporary_file(*args, **kwargs):
        raise AssertionError("不应创建磁盘临时文件")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", reject_disk_temporary_file)
    save_label(LabelFile(), image)
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


@pytest.mark.parametrize("embedded", [None, [], 42, False, '\"文本\"'])
def test_invalid_embedded_object_does_not_override_external_json(tmp_path, embedded):
    image_path = tmp_path / "invalid-annotation.png"
    save_image(image_path)
    save_label(LabelFile(), image_path, label="外部数据")
    write_image_json(image_path, embedded)
    sidecar_path = image_path.with_suffix(".json")
    assert select_annotation_source(image_path, sidecar_path) == sidecar_path
    for source in (image_path, sidecar_path):
        assert LabelFile(str(source)).shapes[0]["label"] == "外部数据"
    assert read_image_json(image_path) == (json.loads(embedded) if isinstance(embedded, str) else embedded)


@pytest.mark.parametrize("entrypoint", ["json", "image"])
@pytest.mark.parametrize("content", ["empty", "broken", "missing"])
def test_external_empty_broken_and_missing_never_read_old_embedded(tmp_path, entrypoint, content):
    image = tmp_path / "sample.png"
    save_image(image)
    save_label(LabelFile(), image, label="旧内嵌")
    sidecar = image.with_suffix(".json")
    if content == "empty":
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["shapes"] = []
        data["flags"] = {}
        sidecar.write_text(json.dumps(data), encoding="utf-8")
    elif content == "broken":
        sidecar.write_text("{", encoding="utf-8")
    else:
        sidecar.unlink()
    originals = {path: path.read_bytes() for path in tmp_path.iterdir()}
    source = sidecar if entrypoint == "json" else image
    if content == "empty":
        assert LabelFile(str(source)).shapes == []
        assert "未统计到任何标签" in folder_count_text(tmp_path)
    else:
        with pytest.raises(LabelFileError):
            LabelFile(str(source))
        assert select_annotation_source(image, sidecar) == (sidecar if content == "broken" else None)
    assert read_image_json(image)["shapes"][0]["label"] == "旧内嵌"
    assert {path: path.read_bytes() for path in originals} == originals


@pytest.mark.parametrize("entrypoint", ["image", "json", "json_with_other_output_dir"])
def test_real_main_window_uses_selected_external_path_and_coordinates(qapp, tmp_path, entrypoint):
    from labelme.config import get_config
    from labelme.dlcv.app import MainWindow

    image = tmp_path / "sample.png"
    save_image(image)
    write_image_json(image, {"imagePath": image.name, "shapes": [annotation_shape("旧内嵌")], "flags": {}})
    labels = tmp_path / "labels"
    labels.mkdir()
    sidecar = image.with_suffix(".json") if entrypoint == "image" else labels / "custom.json"
    expected_points = [[4, 3], [18, 3], [18, 12], [4, 12]]
    sidecar.write_text(json.dumps({"imagePath": image.name if entrypoint == "image" else "../sample.png",
        "imageWidth": 24, "imageHeight": 16,
        "shapes": [{**annotation_shape("外部修改"), "points": expected_points}], "flags": {}}), encoding="utf-8")
    originals = {path: path.read_bytes() for path in (image, sidecar)}
    config = get_config()
    config.update(auto_save=False, keep_prev=False)
    other_output = tmp_path / "other-output"
    other_output.mkdir()
    window = MainWindow(config=config, output_dir=str(other_output) if entrypoint == "json_with_other_output_dir" else None)
    errors = []
    window.errorMessage = lambda title, message: errors.append((title, message))
    try:
        assert window.loadFile(str(image if entrypoint == "image" else sidecar)) is not False
        assert not errors
        assert (window.image.width(), window.image.height()) == (24, 16)
        assert Path(window.labelFile.filename).resolve() == sidecar.resolve()
        assert [item.label for item in window.canvas.shapes] == ["外部修改"]
        assert [[[point.x(), point.y()] for point in item.points] for item in window.canvas.shapes] == [expected_points]
        assert window.hasLabelFile()
        assert {path: path.read_bytes() for path in originals} == originals
    finally:
        window.setClean()
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.fixture
def annotation_window(qapp):
    from labelme.config import get_config
    from labelme.dlcv.app import MainWindow

    windows = []
    def create(*, output_dir=None, keep_previous=False):
        config = get_config()
        config.update(auto_save=False, keep_prev=keep_previous)
        window = MainWindow(config=config, output_dir=output_dir)
        window.actions.saveAuto.setChecked(False)
        window.capture_errors = []
        window.errorMessage = lambda title, message: window.capture_errors.append((title, message))
        windows.append(window)
        return window
    yield create
    for window in windows:
        window.setClean()
        window.close()
        window.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("save_mode", ["manual", "auto"])
def test_custom_json_save_clear_and_reopen_keep_selected_path(tmp_path, annotation_window, save_mode):
    from dlcv_core.image_json import has_image_json

    image = tmp_path / "sample.png"
    save_image(image)
    output = tmp_path / "labels" / "review.json"
    output.parent.mkdir()
    LabelFile().save(str(output), [annotation_shape("原标注")], "../sample.png", 16, 24, flags={})
    window = annotation_window()
    assert window.loadFile(str(output)) is not False
    window._update_item(item=window.labelList.findItemByShape(window.canvas.shapes[0]),
        text="修改后", flags=None, group_id=None, description=None)
    window._config["auto_save"] = save_mode == "auto"
    if save_mode == "manual":
        assert window.saveFile()
    else:
        window.setDirty()
    assert not window.capture_errors
    assert json.loads(output.read_text(encoding="utf-8"))["shapes"][0]["label"] == "修改后"
    assert read_image_json(image)["shapes"][0]["label"] == "修改后"
    assert not image.with_suffix(".json").exists()
    assert window.loadFile(str(output)) is not False
    assert [item.label for item in window.canvas.shapes] == ["修改后"]
    window._config["auto_save"] = False
    window.remLabels(list(window.canvas.shapes))
    window.canvas.shapes = []
    window.flag_widget.clear()
    assert window.saveFile()
    assert not output.exists()
    assert not has_image_json(image)
    assert not window.hasLabelFile()
    assert window.loadFile(str(image)) is not False
    assert window.canvas.shapes == []
    assert not window.capture_errors
    with Image.open(image) as loaded:
        assert loaded.size == (24, 16)


def test_output_directory_tree_filters_count_and_loading_share_external_source(tmp_path, annotation_window):
    from qtpy import QtCore

    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    image = images / "labeled.png"
    embedded_only = images / "embedded-only.png"
    for path in (image, embedded_only):
        save_image(path)
        write_image_json(path, {"imagePath": path.name, "shapes": [annotation_shape("旧内嵌")], "flags": {}})
    output = labels / "labeled.json"
    output.write_text(json.dumps({"imagePath": "../images/labeled.png", "shapes": [annotation_shape("外部")],
        "imageWidth": 24, "imageHeight": 16, "flags": {}}), encoding="utf-8")
    window = annotation_window(output_dir=str(labels))
    window.importDirImages(str(images), load=False)
    assert window.loadFile(str(image)) is not False
    assert [item.label for item in window.canvas.shapes] == ["外部"]
    assert window.hasLabelFile()
    tree = window.fileListWidget.tree_widget
    tree.update_state()
    labeled_item = tree._file_items[image.as_posix()]
    unlabeled_item = tree._file_items[embedded_only.as_posix()]
    assert labeled_item.checkState(0) == QtCore.Qt.Checked
    assert unlabeled_item.checkState(0) == QtCore.Qt.Unchecked
    tree.apply_filters(show_annotated=True, show_unannotated=False)
    assert not labeled_item.isHidden()
    assert unlabeled_item.isHidden()
    window.label_count_dock.count_labels_in_dir()
    text = window.label_count_dock.label_count_text.toPlainText()
    assert "外部: 1" in text
    assert "旧内嵌" not in text
    assert "总数: 1" in text
    assert window.saveFile()
    assert read_image_json(image)["shapes"][0]["label"] == "外部"
    assert not image.with_suffix(".json").exists()
    assert not window.capture_errors


def test_group_save_resolves_json_members_from_json_directory(tmp_path):
    image_dir = tmp_path / "images" / "camera1"
    other_image_dir = tmp_path / "images" / "camera2"
    labels = tmp_path / "labels" / "review"
    for directory in (image_dir, other_image_dir, labels):
        directory.mkdir(parents=True)
    first = image_dir / "first.png"
    second = other_image_dir / "second.png"
    for image in (first, second):
        save_image(image)
    output = labels / "group.json"
    LabelFile().save(str(output), [annotation_shape("跨目录")], "../../images/camera1/first.png", 16, 24,
        otherData={"image_path_list": ["../../images/camera1/first.png", "../../images/camera2/second.png"],
                   "img_name_list": ["first.png", "../camera2/second.png"]}, flags={})
    external = json.loads(output.read_text(encoding="utf-8"))
    assert (labels / external["imagePath"]).resolve() == first
    assert [(labels / name).resolve() for name in external["image_path_list"]] == [first, second]
    assert [(first.parent / name).resolve() for name in external["img_name_list"]] == [first, second]
    for image in (first, second):
        embedded = read_image_json(image)
        assert embedded["imagePath"] == image.name
        assert embedded["shapes"] == external["shapes"] == [annotation_shape("跨目录")]
        for key in ("image_path_list", "img_name_list"):
            assert [(image.parent / name).resolve() for name in embedded[key]] == [first, second]
        assert (embedded["imageWidth"], embedded["imageHeight"]) == (24, 16)
        with Image.open(image) as decoded:
            assert decoded.size == (24, 16)
    assert LabelFile(str(output)).shapes[0]["label"] == "跨目录"


def test_existing_empty_external_stays_empty_with_keep_previous(tmp_path, annotation_window):
    first = tmp_path / "first.png"
    empty = tmp_path / "empty.png"
    for image in (first, empty):
        save_image(image)
        save_label(LabelFile(), image, label="历史标注")
    data = json.loads(empty.with_suffix(".json").read_text(encoding="utf-8"))
    data.update(shapes=[], flags={})
    empty.with_suffix(".json").write_text(json.dumps(data), encoding="utf-8")
    window = annotation_window(keep_previous=True)
    assert window.loadFile(str(first)) is not False
    assert len(window.canvas.shapes) == 1
    assert window.loadFile(str(empty)) is not False
    assert window.labelFile is not None
    assert window.labelFile.shapes == []
    assert window.canvas.shapes == []
    assert not window.capture_errors
    assert read_image_json(empty)["shapes"][0]["label"] == "历史标注"


@pytest.mark.parametrize("save_mode", ["manual", "auto"])
def test_group_save_as_then_continuous_save_reopen_and_clear_keep_paths(tmp_path, annotation_window, save_mode):
    from dlcv_core.image_json import has_image_json

    first = tmp_path / "images" / "camera1" / "first.png"
    second = tmp_path / "images" / "camera2" / "second.png"
    source = tmp_path / "labels" / "old" / "source.json"
    target = tmp_path / "labels" / "final" / "nested" / "review.json"
    for directory in (first.parent, second.parent, source.parent, target.parent):
        directory.mkdir(parents=True)
    for image in (first, second):
        save_image(image)
    LabelFile().save(str(source), [annotation_shape("初始标注")], "../../images/camera1/first.png", 16, 24,
        otherData={"image_path_list": ["../../images/camera1/first.png", "../../images/camera2/second.png"],
                   "img_name_list": ["first.png", "../camera2/second.png"]}, flags={})
    original_source = source.read_bytes()
    window = annotation_window()
    assert window.loadFile(str(source)) is not False

    def check_current(label):
        external = json.loads(target.read_text(encoding="utf-8"))
        assert (target.parent / external["imagePath"]).resolve() == first
        assert [(target.parent / name).resolve() for name in external["image_path_list"]] == [first, second]
        assert [(first.parent / name).resolve() for name in external["img_name_list"]] == [first, second]
        assert external["shapes"][0]["label"] == label
        assert external["shapes"][0]["points"] == [[1, 1], [12, 1], [12, 10], [1, 10]]
        for image in (first, second):
            embedded = read_image_json(image)
            assert embedded["imagePath"] == image.name
            assert embedded["shapes"] == external["shapes"]
            assert (embedded["imageWidth"], embedded["imageHeight"]) == (24, 16)
            for key in ("image_path_list", "img_name_list"):
                assert [(image.parent / name).resolve() for name in embedded[key]] == [first, second]
            assert not image.with_suffix(".json").exists()
        assert source.read_bytes() == original_source
        assert Path(window.labelFile.filename).resolve() == target
        assert not window.capture_errors

    window._update_item(item=window.labelList.findItemByShape(window.canvas.shapes[0]),
        text="另存标注", flags=None, group_id=None, description=None)
    window.saveFileDialog = lambda: str(target)
    assert window.saveFileAs()
    check_current("另存标注")
    window._update_item(item=window.labelList.findItemByShape(window.canvas.shapes[0]),
        text="连续保存", flags=None, group_id=None, description=None)
    window._config["auto_save"] = save_mode == "auto"
    if save_mode == "manual":
        assert window.saveFile()
    else:
        window.setDirty()
    check_current("连续保存")
    assert window.loadFile(str(target)) is not False
    assert [item.label for item in window.canvas.shapes] == ["连续保存"]
    check_current("连续保存")
    window._config["auto_save"] = False
    window.remLabels(list(window.canvas.shapes))
    window.canvas.shapes = []
    window.flag_widget.clear()
    assert window.saveFile()
    assert not target.exists()
    assert source.read_bytes() == original_source
    assert not any(has_image_json(image) for image in (first, second))
    assert not window.hasLabelFile()
    assert window.loadFile(str(first)) is not False
    assert window.canvas.shapes == []
    assert not window.capture_errors


@pytest.mark.parametrize("grouped,save_mode", [(False, "manual"), (False, "auto"), (True, "manual"), (True, "auto")])
def test_true_false_flags_survive_nonstem_save_group_save_as_and_reopen(tmp_path, annotation_window, grouped, save_mode):
    from qtpy import QtCore

    first = tmp_path / "images/camera1/first.png"
    second = tmp_path / "images/camera2/second.png"
    source = tmp_path / "labels/original/review.json"
    target = tmp_path / "elsewhere/saved/deep/final-review.json" if grouped else source
    for directory in (first.parent, second.parent, source.parent, target.parent):
        directory.mkdir(parents=True, exist_ok=True)
    members = [first, second] if grouped else [first]
    for image, size in zip(members, [(24, 16), (36, 24)]):
        Image.new("RGB", size, (20, 80, 160)).save(image)
    pixels = {}
    for member in members:
        with Image.open(member) as image:
            pixels[member] = (image.mode, image.size, image.tobytes())
    expected_flags = {"外部已复核": True, "需复查": False}
    expected_shape_flags = {"已确认": True, "需调整": False}
    data = {"version": "5.5.0", "imagePath": "../../images/camera1/first.png", "imageWidth": 24, "imageHeight": 16,
        "imageData": None, "flags": expected_flags, "shapes": [{**annotation_shape("初始标注"), "flags": expected_shape_flags}],
        "审核批次": "独立测试"}
    if grouped:
        data.update(image_path_list=["../../images/camera1/first.png", "../../images/camera2/second.png"],
                    img_name_list=["first.png", "../camera2/second.png"])
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    original_source = source.read_bytes()
    window = annotation_window()
    assert window.loadFile(str(source)) is not False
    def check_saved(label):
        external = json.loads(target.read_text(encoding="utf-8"))
        assert external["flags"] == expected_flags
        assert external["shapes"][0]["flags"] == expected_shape_flags
        assert external["shapes"][0]["label"] == label
        assert (target.parent / external["imagePath"]).resolve() == first
        assert external["审核批次"] == "独立测试"
        for member in members:
            embedded = read_image_json(member)
            assert embedded["flags"] == expected_flags
            assert embedded["shapes"] == external["shapes"]
            assert embedded["imagePath"] == member.name
            assert (embedded["imageWidth"], embedded["imageHeight"]) == (24, 16)
            if grouped:
                assert [(target.parent / name).resolve() for name in external["image_path_list"]] == members
                assert [(first.parent / name).resolve() for name in external["img_name_list"]] == members
                for key in ("image_path_list", "img_name_list"):
                    assert [(member.parent / name).resolve() for name in embedded[key]] == members
                assert source.read_bytes() == original_source
            with Image.open(member) as image:
                assert (image.mode, image.size, image.tobytes()) == pixels[member]
            assert not member.with_suffix(".json").exists()
        assert Path(window.labelFile.filename).resolve() == target
        assert not window.capture_errors
    if grouped:
        window._update_item(item=window.labelList.findItemByShape(window.canvas.shapes[0]),
            text="另存标注", flags=None, group_id=None, description=None)
        window.saveFileDialog = lambda: str(target)
        assert window.saveFileAs()
        check_saved("另存标注")
    window._config["auto_save"] = save_mode == "auto"
    window.actions.saveAuto.setChecked(save_mode == "auto")
    for label in ("连续第一次", "连续第二次"):
        window._update_item(item=window.labelList.findItemByShape(window.canvas.shapes[0]),
            text=label, flags=None, group_id=None, description=None)
        if save_mode == "manual":
            assert window.saveFile()
        assert window.dirty is False
        check_saved(label)
    window._config["auto_save"] = False
    window.actions.saveAuto.setChecked(False)
    assert window.loadFile(str(target)) is not False
    assert [shape.label for shape in window.canvas.shapes] == ["连续第二次"]
    assert window.canvas.shapes[0].flags == expected_shape_flags
    assert {window.flag_widget.item(index).text(): window.flag_widget.item(index).checkState() == QtCore.Qt.Checked
        for index in range(window.flag_widget.count())} == expected_flags
    check_saved("连续第二次")


@pytest.mark.parametrize("default_exists", [False, True])
def test_selected_json_after_discard_import_stays_current_but_is_not_reused_for_other_actions(tmp_path, annotation_window, monkeypatch, default_exists):
    from qtpy import QtCore, QtWidgets
    from labelme.dlcv.label_file import resolve_sidecar_path

    image_dir = tmp_path / "images"
    selected = tmp_path / "labels/selected/review.json"
    output = tmp_path / "labels/output"
    for directory in (image_dir, selected.parent, output):
        directory.mkdir(parents=True)
    first, other = image_dir / "main.png", image_dir / "other.png"
    for image in (first, other):
        save_image(image)
    def material(image_path, label):
        return {"version": "5.5.0", "imagePath": "../../images/" + image_path.name,
            "imageWidth": 24, "imageHeight": 16, "imageData": None,
            "shapes": [annotation_shape(label)], "flags": {"已复核": True, "需复查": False}}
    selected.write_text(json.dumps(material(first, "选定来源"), ensure_ascii=False), encoding="utf-8")
    if default_exists:
        (output / "main.json").write_text(json.dumps(material(first, "默认来源"), ensure_ascii=False), encoding="utf-8")
    (output / "other.json").write_text(json.dumps(material(other, "另一来源"), ensure_ascii=False), encoding="utf-8")
    originals = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    window = annotation_window(output_dir=str(output))
    assert window.loadFile(str(selected)) is not False
    questions = []
    def discard(parent, title, message, buttons, default):
        assert parent is window
        assert buttons == QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel
        assert default == QtWidgets.QMessageBox.Save
        questions.append(message)
        return QtWidgets.QMessageBox.Discard
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", discard)
    assert window.dirty is True
    window.importDirImages(str(image_dir), load=False)
    assert len(questions) == 1
    assert window.filename is None
    assert [shape.label for shape in window.canvas.shapes] == ["选定来源"]
    assert Path(window.labelFile.sidecar_path).resolve() == selected
    assert resolve_sidecar_path(first, window).resolve() == selected
    assert resolve_sidecar_path(first, window, use_loaded=False).resolve() == output / "main.json"
    assert resolve_sidecar_path(other, window).resolve() == output / "other.json"
    tree = window.fileListWidget.tree_widget
    tree.update_state()
    first_item, other_item = tree._file_items[first.as_posix()], tree._file_items[other.as_posix()]
    assert first_item.checkState(0) == other_item.checkState(0) == QtCore.Qt.Checked
    tree.apply_filters(show_annotated=True, show_unannotated=False)
    assert not first_item.isHidden() and not other_item.isHidden()
    window.label_count_dock.count_labels_in_dir()
    text = window.label_count_dock.label_count_text.toPlainText()
    assert "选定来源: 1" in text and "另一来源: 1" in text
    assert "默认来源" not in text and "需复查:" not in text
    assert "共扫描 2 份标注" in text and "总数: 4" in text
    assert window.loadFile(str(other)) is not False
    assert [shape.label for shape in window.canvas.shapes] == ["另一来源"]
    assert resolve_sidecar_path(first, window).resolve() == output / "main.json"
    tree.update_state()
    first_item, other_item = tree._file_items[first.as_posix()], tree._file_items[other.as_posix()]
    assert first_item.checkState(0) == (QtCore.Qt.Checked if default_exists else QtCore.Qt.Unchecked)
    tree.apply_filters(show_annotated=False, show_unannotated=True)
    assert first_item.isHidden() == default_exists
    assert other_item.isHidden()
    window.label_count_dock.count_labels_in_dir()
    text = window.label_count_dock.label_count_text.toPlainText()
    assert "选定来源" not in text and "另一来源: 1" in text
    assert ("默认来源: 1" in text) == default_exists
    assert window.loadFile(str(first)) is not False
    assert [shape.label for shape in window.canvas.shapes] == (["默认来源"] if default_exists else [])
    if default_exists:
        assert Path(window.labelFile.sidecar_path).resolve() == output / "main.json"
    else:
        assert window.labelFile is None
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert not window.capture_errors
