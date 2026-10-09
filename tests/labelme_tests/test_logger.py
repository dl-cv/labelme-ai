"""日志文件保留既有名称，使用 UTF-8 纯文本记录。"""

import logging
import os

import pytest
from pathlib import Path


def test_file_log_keeps_name_and_formats_arguments_as_plain_utf8(tmp_path):
    """2026-10-09：保存报错没有日志；检查实际文件能够记录异常和完整堆栈。"""
    if os.name != "nt":
        pytest.skip("Windows 文件日志")
    from labelme.logger import logger

    handler = next(item for item in logger.handlers if isinstance(item, logging.FileHandler))
    assert Path(handler.baseFilename).name == "LabelmeAI.log"
    message = f"日志记录检查-{tmp_path.name}"
    try:
        raise PermissionError("图片写入被拒绝")
    except PermissionError:
        logger.exception("%s：保存标注失败", message)
    handler.flush()
    text = Path(handler.baseFilename).read_text(encoding="utf-8")
    entry = text[text.index(message):]
    assert message + "：保存标注失败" in entry
    assert "Traceback" in entry and "PermissionError: 图片写入被拒绝" in entry
    assert "\x1b[" not in entry
