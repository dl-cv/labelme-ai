"""语言文件不可写时，读取与写入都不得中断界面渲染。"""
from labelme.dlcv import dlcv_translator


def _block_parent(tmp_path, monkeypatch):
    """用同名文件占用 %APPDATA%\\dlcv 的上级目录位置，稳定复现创建失败。"""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(blocked))
    return blocked


def test_read_language_survives_unwritable_directory(tmp_path, monkeypatch):
    """目录不可创建时启动读取应回退到简体中文，不抛异常。"""
    _block_parent(tmp_path, monkeypatch)

    assert dlcv_translator._read_language() == "zh-Hans"


def test_write_language_survives_unwritable_directory(tmp_path, monkeypatch):
    """写入失败时返回目标标签，供调用方在本进程内切换语言。"""
    _block_parent(tmp_path, monkeypatch)

    assert dlcv_translator._write_language("en") == "en"
    assert dlcv_translator._write_language("zh-Hans") == "zh-Hans"


def test_read_language_survives_write_failure(tmp_path, monkeypatch):
    """目录可创建但写盘失败（只读、被拦截）时同样不抛异常。"""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    def _raise(*args, **kwargs):
        raise PermissionError("文件被占用")

    monkeypatch.setattr("pathlib.Path.write_text", _raise)

    assert dlcv_translator._read_language() == "zh-Hans"
    assert dlcv_translator._write_language("en") == "en"


def test_translator_keeps_running_without_language_file(tmp_path, monkeypatch):
    """语言文件不可写时，翻译函数仍按本次运行语言返回中文文案。"""
    _block_parent(tmp_path, monkeypatch)
    dlcv_translator.dlcv_tr.lang = None

    assert dlcv_translator.dlcv_tr("使用文档") == "使用文档"
    assert dlcv_translator.dlcv_tr.lang == "zh_CN"
