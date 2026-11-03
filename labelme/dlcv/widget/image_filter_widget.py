"""图像筛选组件：筛选卡片 + 类别扫描 + 筛选状态。

职责划分：
- 本组件负责“类别统计 + 勾选 + 应用/取消 + 与文件树页面切换”；
- 文件树组件只负责按传入的类别/索引隐藏节点。

本组件是 ``ImageFilterPanel``（纯 UI 卡片）的子类，对外通过
``filter_state()`` 提供当前筛选条件，并通过 ``owner.reapply_filters()``
让文件树重新执行过滤。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from qtpy import QtCore

from labelme.dlcv import dlcv_tr
from labelme.dlcv.store import STORE
from labelme.dlcv.ui_style import get_image_filter_toggle_qss
from labelme.dlcv.widget.image_filter_panel import ImageFilterPanel
from labelme.dlcv.widget.image_filter_panel import ImageFilterScanThread
from labelme.dlcv.widget.image_filter_panel import make_filter_icon
from labelme.dlcv.widget.image_filter_panel import read_label_order
from labelme.logger import logger


class ImageFilterWidget(ImageFilterPanel):
    """文件树面板里的“图像筛选”组件。

    Args:
        tree_widget: 文件树控件（提供根目录、扩展名，并负责最终过滤）。
        owner: 文件树面板；筛选状态变化时调用 ``owner.reapply_filters()``。
        toggle_button: 文件树顶部“图像筛选”漏斗按钮。
    """

    sig_open_changed = QtCore.Signal(bool)

    def __init__(self, tree_widget, owner, toggle_button, parent=None):
        super().__init__(parent)
        self._tree = tree_widget
        self._owner = owner
        self._toggle_button = toggle_button
        # 按钮样式随组件生效，不依赖全局主题。
        self._toggle_button.setStyleSheet(get_image_filter_toggle_qss())

        self._index = None  # ImageFilterIndex | None
        self._dirty = False
        self._data_epoch = 0
        self._selected = set()
        self._open = False

        self._scan_thread = None
        self._live_scan_threads = set()
        self._generation = 0
        self._pending_apply = False
        self._pending_selection = None
        self._pending_attempts = 0

        self.sig_apply.connect(self._on_apply_requested)
        self.sig_cancel.connect(self.cancel_filters)
        self.sig_close.connect(self.close_page)
        self._toggle_button.clicked.connect(self.toggle)
        self._update_toggle_button()

        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    # ---------- 对外状态 ----------
    def is_open(self) -> bool:
        return self._open

    def is_dirty(self) -> bool:
        return self._dirty

    def has_active_filter(self) -> bool:
        return bool(self._selected)

    def current_index(self):
        return self._index

    def filter_state(self):
        """返回 (类别集合, 当前索引) 供文件树执行过滤。"""
        return set(self._selected), self._index

    def install_index(self, index, dirty: bool = False):
        """注入现成的扫描结果（便于测试或复用）。"""
        self._index = index
        self._dirty = bool(dirty)
        self._update_toggle_button()

    def set_active_filter(self, categories):
        """直接设置已生效的筛选条件（不经过卡片应用流程）。"""
        self._selected = {label for label in (categories or ()) if label}
        self._update_toggle_button()
        self._owner.reapply_filters()

    def mark_data_changed(self):
        """标注数据发生变化后标记扫描结果过期。"""
        self._dirty = True
        self._data_epoch += 1

    def notify_tree_changed(self):
        """文件树内容变化（刷新/删除/项目类型切换）后调用。"""
        self.mark_data_changed()
        if self.has_active_filter() or self._open:
            self._start_scan(force=True)

    def reset_for_new_root(self):
        """切换文件夹前重置所有筛选状态。"""
        self._shutdown_scan_thread(wait=False)
        self._index = None
        self._dirty = False
        self._selected = set()
        self._pending_apply = False
        self._pending_selection = None
        self._pending_attempts = 0
        self.reset()
        self.close_page()
        self._update_toggle_button()

    def shutdown(self, wait: bool = True):
        """退出/销毁前收尾所有扫描线程。"""
        self._shutdown_scan_thread(wait=wait)

    # ---------- 页面切换 ----------
    def toggle(self):
        if self._open:
            self.close_page()
        else:
            self.open_page()

    def open_page(self):
        if self._open:
            return
        self._open = True
        self.sig_open_changed.emit(True)
        root_dir = self._tree.get_root_dir()
        if not root_dir:
            self.show_message(dlcv_tr("请先打开图片文件夹"))
            self.setFocus()
            return

        if self._index is not None:
            self.set_index(self._index, self._selected)
        if self._index is None or self._dirty:
            self.set_loading(0)
            self._start_scan()
        self.setFocus()

    def close_page(self):
        was_open = self._open
        self._open = False
        self._pending_apply = False
        self._pending_selection = None
        self._pending_attempts = 0
        if was_open:
            self.sig_open_changed.emit(False)

    # ---------- 应用/取消 ----------
    def _on_apply_requested(self, categories):
        pending = {label for label in (categories or ()) if label}
        # 标注刚保存过时扫描结果可能过期：先重新统计，成功后再提交筛选。
        if self._index is not None and self._dirty:
            self._pending_apply = True
            self._pending_selection = pending
            self._pending_attempts = 0
            self.set_loading(0)
            self._start_scan(force=True)
            return
        self._commit_filter(pending)

    def cancel_filters(self):
        """取消筛选并清理界面状态（“取消筛选”按钮 / 外部重置）。"""
        self._selected = set()
        self._pending_apply = False
        self._pending_selection = None
        self._pending_attempts = 0
        self._update_toggle_button()
        self._owner.reapply_filters()
        self.close_page()

    def _commit_filter(self, categories):
        self._selected = {label for label in (categories or ()) if label}
        self._pending_apply = False
        self._pending_selection = None
        self._pending_attempts = 0
        self._update_toggle_button()
        self._owner.reapply_filters()
        self.close_page()

    def _update_toggle_button(self):
        active = self.has_active_filter()
        if self._toggle_button.property("active") != active:
            self._toggle_button.setProperty("active", active)
            style = self._toggle_button.style()
            style.unpolish(self._toggle_button)
            style.polish(self._toggle_button)
            self._toggle_button.update()
        self._toggle_button.setIcon(make_filter_icon(active, 16))

        if active:
            parts = []
            if self._selected:
                parts.append(
                    dlcv_tr("已选类别：{names}").format(
                        names=self._join_labels(self._selected)
                    )
                )
            try:
                lang = dlcv_tr.get_lang() or "zh_CN"
            except Exception:
                lang = "zh_CN"
            separator = "，" if lang == "zh_CN" else ", "
            self._toggle_button.setToolTip(
                dlcv_tr("图像筛选：{summary}").format(
                    summary=separator.join(parts)
                )
            )
        else:
            self._toggle_button.setToolTip(dlcv_tr("按标注类别筛选图片"))

    @staticmethod
    def _join_labels(labels) -> str:
        """按当前界面语言拼接类别名（中文用顿号，英文用逗号）。"""
        try:
            lang = dlcv_tr.get_lang() or "zh_CN"
        except Exception:
            lang = "zh_CN"
        separator = "、" if lang == "zh_CN" else ", "
        return separator.join(sorted(labels))

    # ---------- 扫描 ----------
    def _make_json_path_resolver(self):
        """在 GUI 线程构造不依赖 Qt/主窗口的 JSON 路径解析器，供后台线程使用。"""
        try:
            proj_manager = STORE.main_window.proj_manager
        except (AssertionError, AttributeError):
            return None
        manager = getattr(proj_manager, "current_manager", None)
        if manager is None:
            # 测试替身或旧实现：直接使用项目提供的解析函数。
            get_json_path = getattr(proj_manager, "get_json_path", None)
            return get_json_path if callable(get_json_path) else None
        try:
            from labelme.dlcv.widget_25d_3d.manager import Proj2_5DManager
        except Exception:
            Proj2_5DManager = None
        if Proj2_5DManager is not None and isinstance(manager, Proj2_5DManager):
            # 2.5D 的映射可能在 GUI 线程被替换，后台线程使用快照副本。
            mapping = dict(manager.file_to_json)

            def resolve_2_5d(img_path):
                img = str(Path(img_path).absolute().as_posix())
                json_name = mapping.get(img)
                if json_name:
                    return os.path.join(os.path.dirname(img), json_name)
                return str(Path(img).with_suffix(".json"))

            return resolve_2_5d
        # 2D/3D 的解析只做路径运算，不读写共享状态，可直接使用。
        return manager.get_json_path

    def _start_scan(self, force: bool = False):
        root_dir = self._tree.get_root_dir()
        if not root_dir:
            return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            if not force:
                return
            self._scan_thread.cancel()

        get_json_path = self._make_json_path_resolver()
        if get_json_path is None:
            self.set_error(dlcv_tr("无法读取项目配置"))
            return

        self._generation += 1
        generation = self._generation
        data_epoch = self._data_epoch
        thread = ImageFilterScanThread(
            root_dir,
            get_json_path,
            self._tree.extensions,
            read_label_order(root_dir),
            None,  # 不挂父子关系：线程生命周期由 _live_scan_threads 管理
        )
        thread.generation = generation
        thread.data_epoch = data_epoch
        thread.sig_progress.connect(self._on_scan_progress_signal)
        thread.sig_finished.connect(self._on_scan_finished_signal)
        thread.sig_failed.connect(self._on_scan_failed_signal)

        def _on_thread_finished(thread=thread):
            self._live_scan_threads.discard(thread)

        thread.finished.connect(_on_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._live_scan_threads.add(thread)
        self._scan_thread = thread
        thread.start()
        if self._open:
            self.set_loading(0)

    # 信号槽绑定在 self 上（而非无 receiver 的 lambda），控件销毁后自动断开。
    def _on_scan_progress_signal(self, count: int):
        thread = self.sender()
        self._on_scan_progress(getattr(thread, "generation", -1), count)

    def _on_scan_finished_signal(self, index):
        thread = self.sender()
        self._on_scan_finished(
            getattr(thread, "generation", -1),
            getattr(thread, "data_epoch", -1),
            index,
        )

    def _on_scan_failed_signal(self, message: str):
        thread = self.sender()
        self._on_scan_failed(getattr(thread, "generation", -1), message)

    def _on_scan_progress(self, generation: int, count: int):
        if generation != self._generation:
            return
        if self._open:
            self.update_loading_progress(count)

    def _on_scan_finished(self, generation: int, data_epoch: int, index):
        if generation != self._generation:
            return
        self._scan_thread = None
        if index is None:  # 已取消（正常情况下取消不会发出 finished）
            return

        if index.failed_count or index.dir_error_count:
            logger.warning(
                "图像筛选统计：%d 个标注读取失败，%d 个目录无法读取",
                index.failed_count,
                index.dir_error_count,
            )

        # 扫描期间数据又变过：结果已过期，若正在等待应用筛选则先重扫。
        stale = data_epoch != self._data_epoch
        if stale and self._pending_apply and self._pending_attempts < 3:
            self._pending_attempts += 1
            self._start_scan(force=True)
            return

        self._index = index
        self._dirty = stale

        available = set(index.categories)
        if self._selected - available:
            self._selected &= available

        if self._open:
            self.set_index(index, self._selected)

        if self._pending_apply:
            pending = (
                self._pending_selection
                if self._pending_selection is not None
                else self._selected
            )
            self._pending_apply = False
            self._pending_selection = None
            self._pending_attempts = 0
            self._commit_filter(pending)
            return

        # 索引/选择可能已变化（例如选中类别被剪空），重新应用一次可见性。
        self._update_toggle_button()
        self._owner.reapply_filters()

    def _on_scan_failed(self, generation: int, message: str):
        if generation != self._generation:
            return
        self._scan_thread = None
        self._pending_apply = False
        self._pending_selection = None
        self._pending_attempts = 0
        logger.warning("图像筛选统计失败：%s", message)
        if self._open:
            self.set_error(dlcv_tr("统计类别失败：{error}").format(error=message))

    def _shutdown_scan_thread(self, wait: bool = True):
        threads = set(self._live_scan_threads)
        if self._scan_thread is not None:
            threads.add(self._scan_thread)
        self._scan_thread = None
        self._generation += 1
        self._pending_apply = False
        self._pending_selection = None
        for thread in threads:
            thread.cancel()
        if not wait:
            # 切换文件夹等交互路径不阻塞 UI；线程完成后的结果会被 generation 丢弃。
            return
        deadline = time.monotonic() + 2.0
        for thread in threads:
            if not thread.isRunning():
                continue
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            thread.wait(remaining_ms)
        # 极端情况下（网盘 IO 卡死）宁可强制结束，也不能让 QThread 在运行中被销毁。
        for thread in threads:
            if thread.isRunning():
                thread.terminate()
                thread.wait(1000)
