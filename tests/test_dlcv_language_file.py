from labelme.dlcv import dlcv_translator


def test_language_file_uses_rfc_5646_tags(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    language_file = tmp_path / "dlcv" / "language.txt"

    assert dlcv_translator._read_language() == "zh-Hans"
    assert language_file.read_text(encoding="utf-8") == "zh-Hans"

    assert dlcv_translator._write_language("en") == "en"
    assert dlcv_translator._read_language() == "en"
    assert language_file.read_text(encoding="utf-8") == "en"

    language_file.write_text("ZH-hans", encoding="utf-8")
    assert dlcv_translator._read_language() == "zh-Hans"
    assert language_file.read_text(encoding="utf-8") == "zh-Hans"

    language_file.write_text("zh", encoding="utf-8")
    assert dlcv_translator._read_language() == "zh-Hans"
    assert language_file.read_text(encoding="utf-8") == "zh-Hans"
