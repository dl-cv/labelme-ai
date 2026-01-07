from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for p in paths:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _get_model_dirs() -> list[Path]:
    """
    Model directory resolution for packaged app.

    Priority:
    - <exe_dir>/models  (onedir)
    - <sys._MEIPASS>/models (onefile fallback)
    """
    candidates: list[Path] = []

    # 1) Directory of the executable (onedir).
    try:
        candidates.append(Path(sys.executable).resolve().parent / "models")
    except Exception:
        pass

    # 2) PyInstaller temp extraction dir (onefile).
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            candidates.append(Path(meipass).resolve() / "models")
        except Exception:
            pass

    return _unique_paths(candidates)


def _resolve_missing_model_path(path: Path, model_dirs: list[Path]) -> Path | None:
    if path.is_file():
        return path
    name = path.name
    for d in model_dirs:
        candidate = d / name
        if candidate.is_file():
            return candidate
    return None


def _patch_onnxruntime(model_dirs: list[Path]) -> None:
    """
    Zero-intrusion fix for hard-coded model paths.

    If the code passes an absolute model path (e.g. C:\\dlcv\\bin\\xxx.onnx) that does
    not exist on the target machine, automatically fallback to bundled:
      <exe_dir>/models/<basename>
    """
    try:
        import onnxruntime as ort
    except Exception:
        return

    Original = ort.InferenceSession

    def maybe_fix_path(path_or_bytes: Any) -> Any:
        if isinstance(path_or_bytes, (str, os.PathLike)):
            try:
                p = Path(path_or_bytes)
                fixed = _resolve_missing_model_path(p, model_dirs)
                if fixed is not None:
                    return str(fixed)
            except Exception:
                pass
        return path_or_bytes

    # Prefer class-based patch to preserve isinstance checks.
    try:
        class PatchedInferenceSession(Original):  # type: ignore[misc, valid-type]
            def __init__(self, path_or_bytes: Any, *args: Any, **kwargs: Any):
                super().__init__(maybe_fix_path(path_or_bytes), *args, **kwargs)

        ort.InferenceSession = PatchedInferenceSession  # type: ignore[assignment]
    except Exception:
        def InferenceSession(path_or_bytes: Any, *args: Any, **kwargs: Any):
            return Original(maybe_fix_path(path_or_bytes), *args, **kwargs)

        ort.InferenceSession = InferenceSession  # type: ignore[assignment]


def main() -> int:
    model_dirs = _get_model_dirs()

    _patch_onnxruntime(model_dirs)

    from labelme.__main__ import main as labelme_main

    labelme_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

