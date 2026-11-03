"""断点续标流程：记录当前图片、打开文件夹时恢复、回到第一张。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from qtpy import QtWidgets

from labelme.dlcv import dlcv_tr
from labelme.dlcv.controller.resume_position import ResumePositionStore
from labelme.dlcv.utils_func import ToastPreset
from labelme.dlcv.utils_func import notification

logger = logging.getLogger(__name__)


class ResumeController:
    """把断点续标的 UI/流程从 MainWindow 中拆出来。"""

    def __init__(self, main_window):
        self.main_window = main_window
        self._store = None

    def get_store(self):
        """懒加载续标记录；设置对象在 UI 初始化时可能被重建一次。"""
        settings = self.main_window.settings
        store = self._store
        if store is not None and store.settings is settings:
            return store
        if store is not None:
            store.persist()
        store = ResumePositionStore(settings)
        self._store = store
        return store

    def persist(self):
        try:
            self.get_store().persist()
        except Exception:
            logger.exception("保存断点续标位置失败")

    def remember(self, filename):
        window = self.main_window
        if not filename or window.is_3d or window.is_2_5d:
            return
        try:
            directory = self._current_dataset_dir(filename)
            self.get_store().remember(filename, directory)
        except Exception:
            logger.exception("记录断点续标位置失败")

    def _current_dataset_dir(self, filename):
        """优先把位置记录到当前打开的根目录，兼顾子文件夹图片。"""
        window = self.main_window
        if not window.lastOpenDir:
            return None
        try:
            relative = Path(os.path.abspath(filename)).relative_to(
                Path(os.path.abspath(window.lastOpenDir))
            )
        except (OSError, TypeError, ValueError):
            return None
        return window.lastOpenDir if relative.parts else None

    def restore(self, dirpath):
        """打开文件夹后自动回到该文件夹上次查看的图片。"""
        window = self.main_window
        if not dirpath or window.is_3d or window.is_2_5d:
            return False

        from labelme.dlcv.file_tree_widget import FileTreeWidget

        if not isinstance(window.fileListWidget, FileTreeWidget):
            return False

        saved_path = self.get_store().get(dirpath)
        if not saved_path:
            return False

        try:
            relative = Path(os.path.abspath(saved_path)).relative_to(
                Path(os.path.abspath(dirpath))
            )
        except (OSError, TypeError, ValueError):
            self.get_store().forget(dirpath)
            return False
        if not relative.parts:
            return False

        try:
            item = window.fileListWidget.select_file_path(saved_path)
        except Exception:
            logger.exception("恢复上次标注图片失败")
            item = None

        if item is None:
            if not os.path.isfile(saved_path):
                self.get_store().forget(dirpath)
                return False
            if not window.loadFile(saved_path):
                return False

        if window.filename is None:
            return False

        name = os.path.basename(saved_path)
        window.status(dlcv_tr("已恢复上次标注位置: {name}").format(name=name))
        notification(
            dlcv_tr("已恢复上次标注位置"),
            dlcv_tr("继续查看: {name}").format(name=name),
            ToastPreset.INFORMATION,
            duration=2500,
        )
        return True

    def start_from_first_image(self):
        """回到当前文件夹的第一张图片（快捷键 Ctrl+Home）。"""
        window = self.main_window
        if not window.lastOpenDir:
            return
        first_path = None
        try:
            first_path = window.fileListWidget.first_file_path()
        except Exception:
            logger.exception("获取第一张图片失败")
        if first_path is None:
            image_list = window.imageList or []
            if image_list:
                first_path = image_list[0]
        if not first_path:
            return
        if window.fileListWidget.select_file_path(first_path) is None:
            window.loadFile(first_path)

    def install_actions(self):
        window = self.main_window
        action = QtWidgets.QAction(dlcv_tr("从第一张开始"), window)
        action.setShortcut("Ctrl+Home")
        action.setStatusTip(dlcv_tr("回到当前文件夹的第一张图片"))
        action.triggered.connect(self.start_from_first_image)
        window.addAction(action)
        if hasattr(window, "menus"):
            window.menus.file.addSeparator()
            window.menus.file.addAction(action)
