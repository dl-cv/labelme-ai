import json
import subprocess
import sys
from pathlib import Path


def _read_manifest(pkg_dir: Path) -> dict:
    manifest_path = pkg_dir / "tool-manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _run_exe(pkg_dir: Path, entry: dict) -> int:
    payload_root = pkg_dir / "payload"
    exe_rel = str(entry.get("path", "")).replace("\\", "/")
    workdir_rel = str(entry.get("workingDir", "")).replace("\\", "/")

    if not exe_rel.startswith("payload/"):
        raise RuntimeError(f"Unsupported entry.path (expected payload/...): {exe_rel!r}")

    exe_path = pkg_dir / exe_rel
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)

    cwd = payload_root
    if workdir_rel:
        if not workdir_rel.startswith("payload"):
            raise RuntimeError(
                f"Unsupported entry.workingDir (expected payload...): {workdir_rel!r}"
            )
        cwd = pkg_dir / workdir_rel

    argv = [str(exe_path), *sys.argv[1:]]
    proc = subprocess.run(argv, cwd=str(cwd))
    return int(proc.returncode or 0)


def main() -> int:
    pkg_dir = Path(__file__).resolve().parent
    manifest = _read_manifest(pkg_dir)
    entry = dict(manifest.get("entry") or {})
    kind = str(entry.get("kind") or "").strip().lower()

    if kind == "exe":
        return _run_exe(pkg_dir, entry)

    raise RuntimeError(f"Unsupported entry.kind: {kind!r}")


if __name__ == "__main__":
    raise SystemExit(main())
