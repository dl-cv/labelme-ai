"""多边形标签列表上方的缺陷导航条。

把原来的“缺陷巡检”面板合并进「多边形标签」，不再维护第二份 shape 列表：
类别筛选、上一个/下一个、只看当前类别、自动定位都直接作用于现有 labelList。
"""

from __future__ import annotations

import os
from collections import Counter

from qtpy import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtGui import QKeySequence

from labelme.dlcv import dlcv_tr
from labelme.dlcv.controller.zoom_controller import focus_shape
from labelme.dlcv.utils_func import ToastPreset
from labelme.dlcv.utils_func import notification
from labelme.utils.qt import newIcon


class LabelNavigatorBar(QtWidgets.QWidget):
    """挂在「多边形标签」列表上方的筛选/导航工具条。"""

    REFRESH_DELAY_MS = 30
    AUTO_ZOOM_SETTINGS_KEY = "label_navigator/auto_zoom"
    DEFAULT_AUTO_ZOOM = False

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._category = None
        self._updating = False
        self._applying_visibility = False
        self._item_text_cache = {}
        self._settings = getattr(main_window, "settings", None)
        self._initial_auto_zoom = self._load_auto_zoom()

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)

        self.setObjectName("labelNavigatorBar")
        self._build_ui()
        self._connect_signals()
        self.refresh(reset_category=True)

    def _load_auto_zoom(self):
        if self._settings is None:
            return self.DEFAULT_AUTO_ZOOM
        try:
            value = self._settings.value(
                self.AUTO_ZOOM_SETTINGS_KEY, self.DEFAULT_AUTO_ZOOM, type=bool
            )
        except TypeError:
            value = self._settings.value(
                self.AUTO_ZOOM_SETTINGS_KEY, self.DEFAULT_AUTO_ZOOM
            )
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    # region UI
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 4)
        layout.setSpacing(4)

        first_row = QtWidgets.QHBoxLayout()
        first_row.setContentsMargins(0, 0, 0, 0)
        first_row.setSpacing(6)
        category_label = QtWidgets.QLabel(dlcv_tr("类别"), self)
        category_label.setObjectName("labelNavigatorFieldLabel")
        self.category_combo = QtWidgets.QComboBox(self)
        self.category_combo.setObjectName("labelNavigatorCombo")
        self.category_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.category_combo.setToolTip(
            dlcv_tr("按类别筛选当前图片的缺陷；选中后自动定位到该类第一个缺陷")
        )
        self.prev_btn = QtWidgets.QPushButton(self)
        self.prev_btn.setObjectName("labelNavigatorBtn")
        self.prev_btn.setIcon(newIcon("prev"))
        self.prev_btn.setToolTip(dlcv_tr("上一个缺陷 (Alt+← / Alt+A)"))
        self.next_btn = QtWidgets.QPushButton(self)
        self.next_btn.setObjectName("labelNavigatorBtn")
        self.next_btn.setIcon(newIcon("next"))
        self.next_btn.setToolTip(dlcv_tr("下一个缺陷 (Alt+→ / Alt+D)"))
        self.position_label = QtWidgets.QLabel("0/0", self)
        self.position_label.setObjectName("labelNavigatorPosition")
        self.position_label.setAlignment(Qt.AlignCenter)
        self.position_label.setMinimumWidth(40)
        self.auto_zoom_checkbox = QtWidgets.QCheckBox(
            dlcv_tr("自动定位"), self
        )
        self.auto_zoom_checkbox.setObjectName("labelNavigatorCheck")
        self.auto_zoom_checkbox.setChecked(self._initial_auto_zoom)
        self.auto_zoom_checkbox.setToolTip(
            dlcv_tr("跳转到缺陷时自动放大并居中显示；标签名称过大时按 C 隐藏")
        )

        first_row.addWidget(category_label)
        first_row.addWidget(self.category_combo, 1)
        first_row.addWidget(self.auto_zoom_checkbox)
        first_row.addWidget(self.prev_btn)
        first_row.addWidget(self.next_btn)
        first_row.addSpacing(4)
        first_row.addWidget(self.position_label)
        layout.addLayout(first_row)
    # endregion

    # region 信号
    def _connect_signals(self):
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        self.next_btn.clicked.connect(lambda: self.step(1))
        self.auto_zoom_checkbox.toggled.connect(self._on_auto_zoom_toggled)

        window = self.main_window
        self.labelList = window.labelList
        self.labelList.setToolTip(
            dlcv_tr(
                "点击缺陷可放大定位；Alt+←/→ 或 Alt+A/D 逐个切换，到首尾自动翻图"
            )
        )
        self.labelList.itemSelectionChanged.connect(self._on_label_selection_changed)
        self.labelList.itemChanged.connect(self._on_label_item_changed)
        model = self.labelList.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(self._schedule_refresh)
        if hasattr(window.canvas, "selectionChanged"):
            window.canvas.selectionChanged.connect(self._on_canvas_selection_changed)

        self.prev_action = QtWidgets.QAction(dlcv_tr("上一个缺陷"), window)
        self.prev_action.setShortcuts(
            [QKeySequence("Alt+Left"), QKeySequence("Alt+A")]
        )
        self.prev_action.triggered.connect(lambda: self._shortcut_step(-1))
        window.addAction(self.prev_action)

        self.next_action = QtWidgets.QAction(dlcv_tr("下一个缺陷"), window)
        self.next_action.setShortcuts(
            [QKeySequence("Alt+Right"), QKeySequence("Alt+D")]
        )
        self.next_action.triggered.connect(lambda: self._shortcut_step(1))
        window.addAction(self.next_action)

    def _shortcut_step(self, delta):
        if self.isVisible():
            self.step(delta)

    def _on_auto_zoom_toggled(self, checked=False):
        if self._settings is not None:
            self._settings.setValue(self.AUTO_ZOOM_SETTINGS_KEY, bool(checked))
        if checked:
            item = self._current_item()
            if item is not None and item.shape() is not None:
                focus_shape(self.main_window, item.shape(), auto_zoom=True)
        self._update_controls()

    def _on_label_item_changed(self, item=None):
        if self._updating or self._applying_visibility or item is None:
            return
        previous = self._item_text_cache.get(item)
        current = item.text()
        if previous == current:
            return
        self._item_text_cache[item] = current
        self._schedule_refresh()

    def _on_label_selection_changed(self, selected, deselected):
        self._update_controls()
        shapes = [
            item.shape()
            for item in selected
            if item is not None and item.shape() is not None
        ]
        if self._updating or self.main_window._noSelectionSlot:
            return
        if len(shapes) == 1 and self.auto_zoom_checkbox.isChecked():
            focus_shape(self.main_window, shapes[0], auto_zoom=True)

    def _on_canvas_selection_changed(self, selected_shapes):
        if self._updating or not selected_shapes or len(selected_shapes) != 1:
            return
        # 画布选中变化由主窗同步 labelList，这里只负责刷新位置计数。
        self._update_controls()

    def _schedule_refresh(self, *args):
        if self._updating:
            return
        self._refresh_timer.start(self.REFRESH_DELAY_MS)
    # endregion

    # region 刷新
    def refresh(self, reset_category=False):
        """按当前 labelList 重建类别下拉，并重新应用行过滤。"""
        if self._updating:
            return
        items = [item for item in self.labelList if item.shape() is not None]
        counts = Counter(
            item.shape().label for item in items if item.shape().label
        )
        self._category = None if reset_category else self._category

        self._updating = True
        try:
            self._rebuild_categories(counts, sum(counts.values()))
            self._apply_row_filter()
            self._apply_category_visibility()
            self._rebuild_text_cache(items)
            self._update_controls()
        finally:
            self._updating = False

    def on_image_loaded(self):
        """切换图片后刷新；保留当前类别，方便连续复核同一类缺陷。"""
        self.refresh()

    def on_folder_changed(self):
        """切换到新文件夹时回到“全部”。"""
        self._category = None

    def _rebuild_categories(self, counts, total):
        combo = self.category_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem(dlcv_tr("全部 ({count})").format(count=total), None)
            for label, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            ):
                combo.addItem(f"{label} ({count})", label)
            if self._category is None:
                combo.setCurrentIndex(0)
            else:
                index = combo.findData(self._category)
                if index < 0:
                    combo.addItem(f"{self._category} (0)", self._category)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
        finally:
            combo.blockSignals(False)
        combo.setEnabled(total > 0)

    def _apply_row_filter(self):
        current = self._current_item()
        for row, item in enumerate(self.labelList):
            shape = item.shape()
            visible = self._category is None or (
                shape is not None and shape.label == self._category
            )
            self.labelList.setRowHidden(row, not visible)
        if current is not None:
            row = self._row_of_item(current)
            if row < 0 or self.labelList.isRowHidden(row):
                blocker = QtCore.QSignalBlocker(self.labelList)
                try:
                    self.labelList.clearSelection()
                    self.labelList.setCurrentIndex(QtCore.QModelIndex())
                finally:
                    del blocker

    def _apply_category_visibility(self):
        """切换类别后同步画布：全部显示全部，具体类别只显示该类。"""
        if self._applying_visibility:
            return
        self._applying_visibility = True
        try:
            for item in self.labelList:
                shape = item.shape()
                visible = self._category is None or (
                    shape is not None and shape.label == self._category
                )
                state = Qt.Checked if visible else Qt.Unchecked
                if item.checkState() != state:
                    item.setCheckState(state)
        finally:
            self._applying_visibility = False
        self.main_window.canvas.update()

    def _update_controls(self):
        visible_items = self._visible_items()
        count = len(visible_items)
        current = self._current_item()
        if current is not None and current in visible_items:
            position = visible_items.index(current) + 1
            self.position_label.setText(f"{position}/{count}")
        else:
            self.position_label.setText(f"0/{count}")

        has_folder = bool(getattr(self.main_window, "lastOpenDir", None))
        has_image = bool(getattr(self.main_window, "filename", None))
        nav_enabled = has_folder and has_image
        self.prev_btn.setEnabled(nav_enabled)
        self.next_btn.setEnabled(nav_enabled)

    def _rebuild_text_cache(self, items):
        self._item_text_cache = {item: item.text() for item in items}
    # endregion

    # region 类别/选择
    def _on_category_changed(self, index):
        if self._updating:
            return
        self._category = (
            self.category_combo.itemData(index) if index >= 0 else None
        )
        self._updating = True
        try:
            self._apply_row_filter()
            self._apply_category_visibility()
            self._update_controls()
        finally:
            self._updating = False

        visible_items = self._visible_items()
        if self._category is not None and visible_items:
            self._jump_to_item(visible_items[0])
        else:
            self._update_controls()

    def _current_item(self):
        index = self.labelList.currentIndex()
        if not index.isValid():
            return None
        return self.labelList.model().itemFromIndex(index)

    def _visible_items(self):
        visible = []
        for row, item in enumerate(self.labelList):
            if not self.labelList.isRowHidden(row):
                visible.append(item)
        return visible

    def _row_of_item(self, item):
        index = self.labelList.model().indexFromItem(item)
        return index.row() if index.isValid() else -1
    # endregion

    # region 跳转
    def step(self, delta):
        """在当前类别可见缺陷内前后切换；越过首尾时自动换图。"""
        if not self.main_window.filename:
            return
        visible_items = self._visible_items()
        if not visible_items:
            self._switch_image(delta)
            return
        current = self._current_item()
        if current not in visible_items:
            self._jump_to_item(visible_items[0 if delta > 0 else -1])
            return
        position = visible_items.index(current)
        next_position = position + delta
        if 0 <= next_position < len(visible_items):
            self._jump_to_item(visible_items[next_position])
            return
        self._switch_image(delta)

    def _switch_image(self, delta):
        main_window = self.main_window
        before = main_window.filename
        if delta > 0:
            main_window.openNextImg()
        else:
            main_window.openPrevImg()

        after = main_window.filename
        if not after or self._same_path(before, after):
            title = (
                dlcv_tr("已经是最后一张图片")
                if delta > 0
                else dlcv_tr("已经是第一张图片")
            )
            notification(title, None, ToastPreset.INFORMATION, duration=2000)
            return

        visible_items = self._visible_items()
        if not visible_items:
            self._notify_no_defect_in_image(delta)
            return
        self._jump_to_item(visible_items[0 if delta > 0 else -1])

    def _notify_no_defect_in_image(self, delta):
        next_word = dlcv_tr("下一张") if delta > 0 else dlcv_tr("上一张")
        if self._category is not None:
            text = dlcv_tr("「{name}」图片没有『{category}』缺陷").format(
                name=next_word, category=self._category
            )
        else:
            text = dlcv_tr("「{name}」图片没有标注").format(name=next_word)
        notification(text, None, ToastPreset.INFORMATION, duration=2000)

    @staticmethod
    def _same_path(first, second):
        if not first or not second:
            return False
        try:
            return os.path.normcase(os.path.abspath(str(first))) == os.path.normcase(
                os.path.abspath(str(second))
            )
        except (OSError, TypeError, ValueError):
            return str(first) == str(second)

    def _jump_to_item(self, item):
        if item is None or item.shape() is None:
            return
        self._updating = True
        try:
            blocker = QtCore.QSignalBlocker(self.labelList)
            try:
                self.labelList.clearSelection()
                index = self.labelList.model().indexFromItem(item)
                self.labelList.setCurrentIndex(index)
                self.labelList.selectItem(item)
                self.labelList.scrollToItem(item)
            finally:
                del blocker
            self._update_controls()
        finally:
            self._updating = False
        focus_shape(
            self.main_window,
            item.shape(),
            auto_zoom=self.auto_zoom_checkbox.isChecked(),
        )
        self._update_controls()
    # endregion
