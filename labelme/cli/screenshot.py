"""运行外部界面验收文件，不包含业务用例。"""
import argparse
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-test", type=Path, required=True, help="外部验收文件")
    parser.add_argument("--ui-native", action="store_true", help="在隔离桌面使用原生窗口")
    parser.add_argument("case_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    script = args.ui_test.resolve()
    if not script.is_file():
        parser.error("验收路径必须是文件")
    if not args.ui_native:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    case_args = args.case_args
    if case_args[:1] == ["--"]:
        case_args = case_args[1:]
    original_args = sys.argv
    try:
        sys.argv = [str(script), *case_args]
        sys.excepthook = sys.__excepthook__
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = original_args


if __name__ == "__main__":
    main()
