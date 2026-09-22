import json

from PIL import Image

from dlcv_core.image_json import read_image_json
from labelme.dlcv.label_file import LabelFile


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


def test_save_writes_image_json_and_removes_sidecar(tmp_path):
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

    assert not sidecar_path.exists()
    data = read_image_json(image_path)
    assert data["shapes"][0]["label"] == "embedded"
    loaded = LabelFile(str(image_path))
    assert loaded.shapes[0]["label"] == "embedded"
    assert loaded.flags == {"ok": True}


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

    assert not sidecar_path.exists()
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
