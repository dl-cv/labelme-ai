"""Windows 日志使用用户目录，以 UTF-8 追加且不包含控制台颜色码。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="仅检查 Windows 日志目录")
@pytest.mark.parametrize("mode", ["appdata", "override", "no_appdata", "empty_appdata"])
def test_windows_log_directory(tmp_path, mode):
    env = os.environ.copy()
    env.pop("LABELME_LOG_DIR", None)
    env["APPDATA"] = str(tmp_path / "应用数据")
    env["USERPROFILE"] = str(tmp_path / "用户目录")
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["FORCE_COLOR"] = "1"
    env.pop("NO_COLOR", None)
    env.pop("ANSI_COLORS_DISABLED", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    expected_dir = Path(env["APPDATA"]) / "dlcv"
    if mode == "override":
        expected_dir = tmp_path / "指定日志"
        env["LABELME_LOG_DIR"] = str(expected_dir)
    elif mode in ("no_appdata", "empty_appdata"):
        if mode == "no_appdata":
            env.pop("APPDATA")
        else:
            env["APPDATA"] = ""
        expected_dir = Path(env["USERPROFILE"]) / "AppData" / "Roaming" / "dlcv"

    expected_log = expected_dir / "LabelmeAI.log"
    assert not expected_dir.exists()
    message = "日志编码检查：保存标签，中文目录，🙂"
    code = (
        "import logging; from labelme.logger import file_handler, logger; "
        "print(file_handler.baseFilename); print(file_handler.encoding); "
        f"logger.info('%s', {message!r}); logging.shutdown()"
    )
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-X", "utf8=0", "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        assert result.stdout.splitlines() == [str(expected_log), "utf-8"]
    data = expected_log.read_bytes()
    assert b"\x1b[" not in data
    text = data.decode("utf-8")
    assert text.count(message) == 2
    assert "\ufffd" not in text
