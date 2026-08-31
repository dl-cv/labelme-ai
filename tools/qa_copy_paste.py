#!/usr/bin/env python
"""Copy/paste 质量门禁：覆盖率 + cosmic-ray 变异测试。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / ".qa-reports"
COVER_TARGET = "labelme.dlcv.utils.clip_paste"
COVER_FILE = "labelme/dlcv/utils/clip_paste.py"
COVER_THRESHOLD = 90.0
MUTATION_THRESHOLD = 80.0
TEST_PATHS = [
    "tests/labelme_tests/dlcv_tests/test_clip_paste.py",
    "tests/labelme_tests/dlcv_tests/test_clipboard_shapes.py",
    "tests/labelme_tests/dlcv_tests/test_copy_paste_gherkin.py",
]
CR_CONFIG = ROOT / "tools" / "cosmic-ray-copy-paste.toml"
CR_SESSION = REPORT_DIR / "copy-paste.cr.sqlite"


def run(cmd, **kwargs):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=ROOT, check=False, **kwargs)


def coverage():
    REPORT_DIR.mkdir(exist_ok=True)
    json_path = REPORT_DIR / "coverage-copy-paste.json"
    env = os.environ.copy()
    env["MPLBACKEND"] = "agg"
    result = run(
        [
            sys.executable,
            "-m",
            "pytest",
            *TEST_PATHS,
            f"--cov={COVER_TARGET}",
            "--cov-report=term-missing",
            f"--cov-report=json:{json_path}",
            "-q",
        ],
        env=env,
    )
    if result.returncode != 0:
        return False, 0.0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    pct = None
    for path, info in data.get("files", {}).items():
        if path.replace("\\", "/").endswith(COVER_FILE):
            pct = info["summary"]["percent_covered"]
            break
    if pct is None:
        pct = data.get("totals", {}).get("percent_covered", 0.0)
    print(f"coverage {COVER_FILE}: {pct:.2f}% (threshold {COVER_THRESHOLD}%)")
    return pct >= COVER_THRESHOLD, pct


def mutation():
    REPORT_DIR.mkdir(exist_ok=True)
    if CR_SESSION.exists():
        CR_SESSION.unlink()
    init = run(["cosmic-ray", "init", str(CR_CONFIG), str(CR_SESSION)])
    if init.returncode != 0:
        return False, 0.0
    exe = run(["cosmic-ray", "exec", str(CR_CONFIG), str(CR_SESSION)])
    dump = subprocess.run(
        ["cr-report", str(CR_SESSION)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    body = (dump.stdout or "") + (dump.stderr or "")
    (REPORT_DIR / "mutation-copy-paste.txt").write_text(body, encoding="utf-8")
    killed = survived = total = 0
    m = re.search(r"total jobs:\s*(\d+)", body, re.I)
    if m:
        total = int(m.group(1))
    m = re.search(r"complete:\s*(\d+)\s+\(([\d.]+)%\)", body, re.I)
    surviving = re.findall(r"surviving mutants:\s*(\d+)", body, re.I)
    if surviving:
        survived = int(surviving[0])
    # cosmic-ray report typical:
    # job counts:
    #         total jobs: 123
    #         complete: 123 (100.00%)
    kills = re.search(r"kills:\s*(\d+)", body, re.I)
    if kills:
        killed = int(kills.group(1))
    else:
        killed = max(total - survived, 0)
    if total <= 0:
        # fallback: count WORK_ITEM lines from dump
        dump_json = subprocess.run(
            ["cosmic-ray", "dump", str(CR_SESSION)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        rows = [ln for ln in (dump_json.stdout or "").splitlines() if ln.strip()]
        total = len(rows) or 1
        killed = sum(1 for ln in rows if "killed" in ln.lower())
        survived = total - killed
    rate = 100.0 * killed / max(total, 1)
    payload = {
        "killed": killed,
        "survived": survived,
        "total": total,
        "kill_rate": rate,
        "init_exit": init.returncode,
        "exec_exit": exe.returncode,
        "report": body[-4000:],
    }
    (REPORT_DIR / "mutation-copy-paste.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"mutation kill rate: {rate:.2f}% "
        f"({killed}/{total}, threshold {MUTATION_THRESHOLD}%)"
    )
    return rate >= MUTATION_THRESHOLD, rate


def main():
    ok_cov, pct = coverage()
    ok_mut, rate = mutation()
    summary = {
        "coverage_ok": ok_cov,
        "coverage_pct": pct,
        "coverage_threshold": COVER_THRESHOLD,
        "mutation_ok": ok_mut,
        "mutation_kill_rate": rate,
        "mutation_threshold": MUTATION_THRESHOLD,
    }
    (REPORT_DIR / "copy-paste-qa-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if not (ok_cov and ok_mut):
        sys.exit(1)


if __name__ == "__main__":
    main()
