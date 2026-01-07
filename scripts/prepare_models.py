from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen


MODELS = [
    {
        "filename": "efficient_sam_vits_encoder.onnx",
        "url": "https://github.com/labelmeai/efficient-sam/releases/download/onnx-models-20231225/efficient_sam_vits_encoder.onnx",
        "md5": "7d97d23e8e0847d4475ca7c9f80da96d",
    },
    {
        "filename": "efficient_sam_vits_decoder.onnx",
        "url": "https://github.com/labelmeai/efficient-sam/releases/download/onnx-models-20231225/efficient_sam_vits_decoder.onnx",
        "md5": "d9372f4a7bbb1a01d236b0508300b994",
    },
]


def _md5sum(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "LabelmeAI/prepare_models"})
    with urlopen(req) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f)


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare offline AI model assets.")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("assets/models"),
        help="Target directory to place model files (default: assets/models).",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Optional source directory to copy model files from (e.g. C:/dlcv/bin).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Disable downloading; fail if files are missing from --source-dir.",
    )
    parser.add_argument(
        "--skip-md5",
        action="store_true",
        help="Skip MD5 validation.",
    )
    args = parser.parse_args()

    model_dir: Path = args.model_dir
    source_dir: Path | None = args.source_dir
    allow_download = not args.no_download
    check_md5 = not args.skip_md5

    model_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    for m in MODELS:
        filename = m["filename"]
        url = m["url"]
        expected_md5 = m.get("md5")

        dst = model_dir / filename
        if dst.is_file():
            if check_md5 and expected_md5:
                got = _md5sum(dst)
                if got.lower() != expected_md5.lower():
                    errors.append(
                        f"MD5 mismatch for {dst} (expected {expected_md5}, got {got})"
                    )
            continue

        copied = False
        if source_dir is not None:
            src = source_dir / filename
            if src.is_file():
                print(f"[prepare_models] Copying: {src} -> {dst}")
                _copy(src, dst)
                copied = True

        if not copied:
            if not allow_download:
                errors.append(
                    f"Missing model file: {dst} (and not found in --source-dir)"
                )
                continue
            print(f"[prepare_models] Downloading: {url} -> {dst}")
            try:
                _download(url, dst)
            except Exception as e:
                errors.append(f"Download failed for {url}: {e}")
                continue

        if check_md5 and expected_md5 and dst.is_file():
            got = _md5sum(dst)
            if got.lower() != expected_md5.lower():
                errors.append(
                    f"MD5 mismatch for {dst} (expected {expected_md5}, got {got})"
                )

    if errors:
        for e in errors:
            print(f"[prepare_models][ERROR] {e}", file=sys.stderr)
        return 2

    print(f"[prepare_models] Done. Models are ready in: {model_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

