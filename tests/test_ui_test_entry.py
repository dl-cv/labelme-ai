import os
from pathlib import Path
import subprocess
import sys


REPOSITORY = Path(__file__).resolve().parents[1]


def run_entry(arguments):
    return subprocess.run(
        [sys.executable, "-m", "labelme", *arguments],
        cwd=REPOSITORY, env=os.environ.copy(), capture_output=True,
        text=True, encoding="utf-8", timeout=30,
    )


def test_missing_ui_script_exits_without_dialog(tmp_path):
    result = run_entry(["--ui-test", str(tmp_path / "missing.py")])

    assert result.returncode == 2
    assert "验收路径必须是文件" in result.stderr


def test_ui_script_receives_its_own_arguments(tmp_path):
    script = tmp_path / "case.py"
    script.write_text(
        "import os, sys\n"
        "assert sys.argv[1:] == ['--case-option', 'value']\n"
        "assert os.environ['QT_QPA_PLATFORM'] == 'offscreen'\n"
        "print('external_case_passed')\n",
        encoding="utf-8",
    )
    result = run_entry(["--ui-test", str(script), "--", "--case-option", "value"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "external_case_passed" in result.stdout
