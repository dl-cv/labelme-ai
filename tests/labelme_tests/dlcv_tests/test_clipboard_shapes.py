import json
import os

import pytest

from labelme.dlcv.widget import clipboard as clipboard_mod


def test_copy_paste_shapes_json_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard_mod.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(clipboard_mod, "copy_file_to_clipboard", lambda path: None)

    shapes = [
        {
            "label": "dog",
            "points": [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
            "shape_type": "polygon",
            "group_id": None,
            "description": "",
            "flags": {},
            "mask": None,
        }
    ]
    clipboard_mod.copy_shapes_to_clipboard(shapes, source_image_path="/img/a.png")
    loaded = clipboard_mod.paste_shapes_from_clipboard()
    assert loaded is not None
    assert loaded[0]["source_image_path"] == "/img/a.png"
    assert loaded[0]["label"] == "dog"
    assert os.path.exists(os.path.join(str(tmp_path), "copied_shapes.json"))


def test_clear_copied_shapes(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard_mod.tempfile, "gettempdir", lambda: str(tmp_path))
    path = tmp_path / "copied_shapes.json"
    path.write_text("[]", encoding="utf-8")
    clipboard_mod.clear_copied_shapes()
    assert not path.exists()
    clipboard_mod.clear_copied_shapes()


def test_paste_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard_mod.tempfile, "gettempdir", lambda: str(tmp_path))
    assert clipboard_mod.paste_shapes_from_clipboard() is None


def test_paste_invalid_json_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard_mod.tempfile, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "copied_shapes.json").write_text("{not-json", encoding="utf-8")
    assert clipboard_mod.paste_shapes_from_clipboard() is None


def test_copy_writes_json_even_when_os_clipboard_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(clipboard_mod.tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(_path):
        raise OSError("no clipboard")

    monkeypatch.setattr(clipboard_mod, "copy_file_to_clipboard", boom)
    with pytest.raises(OSError):
        clipboard_mod.copy_shapes_to_clipboard([{"label": "x"}], "/img.png")
    data = json.loads((tmp_path / "copied_shapes.json").read_text(encoding="utf-8"))
    assert data[0]["source_image_path"] == "/img.png"
