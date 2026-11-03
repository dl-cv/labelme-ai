"""断点续标：按文件夹记住上一次查看的图片。

用户反馈：一个文件夹里的缺陷改到一半，重新打开时又从第一张开始看，
需要能回到上次停下的位置。这里只负责持久化“文件夹 -> 图片”的映射，
真正的跳转由主窗在导入目录后完成。
"""

from __future__ import annotations

import json
import os
from typing import Optional

SETTINGS_KEY = "resume/last_image_by_dir"
MAX_DIRS = 30


def normalize_path(path) -> str:
    """把路径规范化为绝对路径，保留原始大小写供加载使用。"""
    if path is None:
        return ""
    try:
        return os.path.normpath(os.path.abspath(os.fspath(path)))
    except (OSError, TypeError, ValueError):
        return ""


def normalize_dir(path) -> str:
    """文件夹作为键时按系统规则忽略大小写。"""
    return os.path.normcase(normalize_path(path))


class ResumePositionStore:
    """QSettings 中的“文件夹 -> 上次图片”记录。"""

    def __init__(self, settings, max_dirs: int = MAX_DIRS):
        self.settings = settings
        self.max_dirs = max(1, int(max_dirs))
        self._positions: Optional[dict] = None

    # region 读写
    def _load(self) -> dict:
        if self._positions is not None:
            return self._positions

        raw = self.settings.value(SETTINGS_KEY, "")
        data = {}
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                loaded = json.loads(raw)
            except (TypeError, ValueError):
                loaded = None
            if isinstance(loaded, dict):
                data = loaded

        positions = {}
        for directory, file_path in data.items():
            normalized_dir = normalize_dir(directory)
            normalized_file = normalize_path(file_path)
            if normalized_dir and normalized_file:
                positions[normalized_dir] = normalized_file
        self._positions = positions
        return positions

    def remember(self, filename, directory=None) -> bool:
        """记录某张图片所在文件夹的续标位置。

        directory 是可选的文件夹键（例如用户打开的数据集根目录），
        用于把子文件夹里的图片也记录到本次打开的根目录上。
        """
        file_path = normalize_path(filename)
        if not file_path or not os.path.isfile(file_path):
            return False

        positions = self._load()
        key = normalize_dir(directory) if directory else normalize_dir(
            os.path.dirname(file_path)
        )
        if not key:
            return False
        positions.pop(key, None)
        positions[key] = file_path
        while len(positions) > self.max_dirs:
            positions.pop(next(iter(positions)))
        return True

    def get(self, directory) -> Optional[str]:
        """返回该文件夹上次查看且仍然存在的图片。"""
        positions = self._load()
        file_path = positions.get(normalize_dir(directory))
        if file_path and os.path.isfile(file_path):
            return file_path
        return None

    def forget(self, directory) -> None:
        self._load().pop(normalize_dir(directory), None)

    def persist(self) -> None:
        """把内存中的记录写回 QSettings。"""
        if self._positions is None:
            return
        payload = json.dumps(self._positions, ensure_ascii=False)
        self.settings.setValue(SETTINGS_KEY, payload)
    # endregion
