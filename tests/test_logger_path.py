"""Windows 日志使用用户目录，并保留自定义目录及追加写入。"""

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
    env["PYTHONUTF8"] = "1"
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
    code = (
        "import logging; from labelme.logger import file_handler, logger; "
        "print(file_handler.baseFilename); "
        "logger.info('log-path-check'); logging.shutdown()"
    )
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        assert str(expected_log) in result.stdout.splitlines()
    assert expected_log.read_text(encoding="utf-8").count("log-path-check") == 2
