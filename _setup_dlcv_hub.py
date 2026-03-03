import os
from pathlib import Path

from setuptools import find_packages, setup


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _collect_package_data(pkg_dir: Path) -> list[str]:
    files: list[str] = []
    tool_manifest = pkg_dir / "tool-manifest.json"
    if tool_manifest.exists():
        files.append("tool-manifest.json")

    payload_dir = pkg_dir / "payload"
    if payload_dir.exists():
        for p in payload_dir.rglob("*"):
            if p.is_file():
                files.append(str(p.relative_to(pkg_dir)).replace("\\", "/"))
    return files


PACKAGE_NAME = _require_env("DLCV_HUB_PACKAGE_NAME")
VERSION = _require_env("DLCV_HUB_VERSION")

HERE = Path(__file__).resolve().parent
PKG_DIR = HERE / "whl" / PACKAGE_NAME

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    description="DLCV Hub tool wheel",
    package_dir={"": "whl"},
    packages=find_packages("whl"),
    include_package_data=True,
    package_data={PACKAGE_NAME: _collect_package_data(PKG_DIR)},
    python_requires=">=3.9",
)
