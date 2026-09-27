from labelme.dlcv import dlcv_translator


def test_language_file_is_the_only_persistent_source(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    language_file = tmp_path / "dlcv" / "language.txt"

    assert dlcv_translator._read_language() == "zh"
    assert language_file.read_text(encoding="utf-8") == "zh"

    assert dlcv_translator._write_language("en_US") == "en"
    assert dlcv_translator._read_language() == "en"
    assert language_file.read_text(encoding="utf-8") == "en"

    language_file.write_text("invalid", encoding="utf-8")
    assert dlcv_translator._read_language() == "zh"
    assert language_file.read_text(encoding="utf-8") == "zh"
