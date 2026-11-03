"""文件树过滤：条件对象 + 应用到 QTreeWidget 的执行器。

- ``FileTreeFilter``：不可变过滤条件（搜索文本、标注状态、类别），
  负责判断单张图片是否可见；
- ``TreeFilter``：把条件应用到文件树（遍历节点、批量隐藏、目录可见性、
  标注存在性按目录缓存、恢复本功能隐藏过的目录）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from qtpy import QtWidgets
from qtpy.QtCore import Qt


def _default_path_key(path) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(Path(os.fspath(path)).absolute().as_posix())
    except (OSError, TypeError, ValueError):
        return ""


@dataclass(frozen=True)
class FileTreeFilter:
    search_text: str = ""
    show_annotated: bool = False
    show_unannotated: bool = False
    categories: frozenset[str] = frozenset()
    index: object = field(default=None, compare=False, repr=False)

    @property
    def category_active(self) -> bool:
        """是否启用了类别筛选。"""
        return bool(self.categories)

    @property
    def annotation_filter_active(self) -> bool:
        """是否只显示已标注或只显示未标注。"""
        return self.show_annotated != self.show_unannotated

    def labels_for(self, image_path):
        if self.index is None:
            return None
        return self.index.labels_for(image_path)

    def matches(self, image_path: str, is_annotated) -> bool:
        """判断图片是否可见。

        Args:
            image_path: 图片路径（文件名过滤按完整路径做子串匹配，与原逻辑一致）。
            is_annotated: 惰性回调，仅在需要判断标注状态时才会被调用（避免无谓 IO）。
        """
        if self.search_text and self.search_text not in image_path:
            return False

        if self.category_active:
            labels = self.labels_for(image_path)
            if labels is None or not labels & self.categories:
                return False

        if self.annotation_filter_active:
            annotated = bool(is_annotated(image_path))
            return annotated if self.show_annotated else not annotated
        return True

    def matched_directories(self):
        """类别筛选时返回有匹配图片的目录集合；未启用时返回 None。"""
        if not self.category_active or self.index is None:
            return None
        return self.index.matched_directories(self.categories)


class TreeFilter:
    """把 ``FileTreeFilter`` 应用到文件树上的执行器。"""

    def __init__(self, tree_widget, file_items_provider, path_key=None):
        """
        Args:
            tree_widget: 目标 QTreeWidget。
            file_items_provider: 无参回调，返回 {图片路径: 文件节点}。
            path_key: 路径归一化函数（默认与图片筛选索引使用同一规则）。
        """
        self._tree = tree_widget
        self._file_items_provider = file_items_provider
        self._path_key = path_key or _default_path_key
        self._criteria = FileTreeFilter()
        self._hidden_dirs = set()

    # ---------- 对外状态 ----------
    @property
    def criteria(self) -> FileTreeFilter:
        return self._criteria

    def apply(self, criteria: FileTreeFilter):
        """应用过滤条件：一次遍历所有已加载文件节点。"""
        self._criteria = criteria
        matched_dirs = criteria.matched_directories()
        is_annotated = self._make_annotation_checker()

        self._tree.setUpdatesEnabled(False)
        try:
            for image_path, item in list(self._file_items_provider().items()):
                item.setHidden(
                    not criteria.matches(image_path, is_annotated)
                )
        finally:
            self._tree.setUpdatesEnabled(True)
        self._apply_directory_visibility(matched_dirs)

    def apply_to_item(self, item, criteria: FileTreeFilter):
        """只更新单个节点（懒加载/勾选状态变化时使用）。"""
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        if path in self._file_items_provider():
            # 单个节点用轻量判断，避免为了一张图重新扫描整个目录。
            if criteria.annotation_filter_active:
                is_annotated = self._is_annotated_now
            else:
                is_annotated = self._never_annotated
            item.setHidden(not criteria.matches(path, is_annotated))
            return

        matched_dirs = criteria.matched_directories()
        if matched_dirs is None:
            return
        hidden = self._path_key(path) not in matched_dirs
        item.setHidden(hidden)
        if hidden:
            self._hidden_dirs.add(path)
        else:
            self._hidden_dirs.discard(path)

    def reset(self):
        """清空过滤条件：恢复所有文件可见，并恢复本功能隐藏过的目录。"""
        self.apply(FileTreeFilter())

    # ---------- 标注存在性 ----------
    @staticmethod
    def _never_annotated(_img_path: str) -> bool:
        return False

    @staticmethod
    def _is_annotated_now(img_path: str) -> bool:
        try:
            from labelme.dlcv.store import STORE

            json_path = STORE.main_window.proj_manager.get_json_path(img_path)
        except Exception:
            return False
        return bool(json_path) and os.path.exists(json_path)

    def _make_annotation_checker(self):
        """按目录缓存 JSON 文件名，避免过滤时每张图一次 exists/stat。"""
        try:
            from labelme.dlcv.store import STORE

            get_json_path = STORE.main_window.proj_manager.get_json_path
        except (AssertionError, AttributeError, ImportError):
            return lambda _img_path: False

        names_by_dir = {}

        def is_annotated(img_path: str) -> bool:
            try:
                json_path = get_json_path(img_path)
            except Exception:
                return False
            directory = os.path.dirname(json_path)
            names = names_by_dir.get(directory)
            if names is None:
                try:
                    names = {
                        entry.name.lower() for entry in os.scandir(directory)
                    }
                except OSError:
                    names = set()
                names_by_dir[directory] = names
            return os.path.basename(json_path).lower() in names

        return is_annotated

    # ---------- 目录可见性 ----------
    def _apply_directory_visibility(self, matched_dirs) -> None:
        """统一处理目录可见性：没有匹配内容的空文件夹隐藏。

        - 类别筛选：只保留扫描结果中“有匹配图片”的目录；
        - 文件名搜索：只保留已加载且存在可见文件的目录（未展开目录内容未知，保持可见）；
        - 取消筛选时只恢复本功能隐藏过的目录，不影响其他机制。
        """
        criteria = self._criteria
        category_active = criteria.category_active and matched_dirs is not None
        text_active = bool(criteria.search_text)

        if not category_active and not text_active:
            self._restore_hidden_directories()
            return

        hidden_now = set()

        def visit(parent):
            """返回 (是否存在可见文件, 目录内容是否已全部加载)。"""
            has_visible = False
            fully_loaded = True
            for row in range(parent.childCount()):
                child = parent.child(row)
                path = child.data(0, Qt.UserRole)
                if not path:
                    # 占位符：懒加载目录内容未知，按“有内容”处理并保持可见。
                    fully_loaded = False
                    continue
                if path in self._file_items_provider():
                    if not child.isHidden():
                        has_visible = True
                    continue

                child_visible, child_loaded = visit(child)
                hidden = False
                if category_active and self._path_key(path) not in matched_dirs:
                    hidden = True
                elif text_active and child_loaded and not child_visible:
                    hidden = True
                child.setHidden(hidden)
                if hidden:
                    hidden_now.add(path)
                else:
                    if child_visible:
                        has_visible = True
                    if not child_loaded:
                        fully_loaded = False
            return has_visible, fully_loaded

        visit(self._tree.invisibleRootItem())
        self._hidden_dirs = hidden_now

    def _restore_hidden_directories(self) -> None:
        if not self._hidden_dirs:
            return
        iterator = QtWidgets.QTreeWidgetItemIterator(self._tree)
        while iterator.value():
            item = iterator.value()
            iterator += 1
            path = item.data(0, Qt.UserRole)
            if path and path in self._hidden_dirs:
                item.setHidden(False)
        self._hidden_dirs.clear()
