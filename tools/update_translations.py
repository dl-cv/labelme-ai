"""从 Qt 翻译源生成运行时使用的 QM 与 Python 资源。"""

import argparse
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lrelease", default=shutil.which("lrelease"))
    args = parser.parse_args()
    if not args.lrelease:
        parser.error("未找到 lrelease，请通过 --lrelease 指定")
    directory = Path(__file__).resolve().parents[1] / "labelme" / "translate"
    source = directory / "zh_CN.ts"
    binary = directory / "zh_CN.qm"
    subprocess.run([args.lrelease, str(source), "-qm", str(binary)], check=True)
    (directory / "zh_CN.py").write_text(
        "# 由 tools/update_translations.py 生成。\n"
        f"translate_data = {binary.read_bytes()!r}\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
