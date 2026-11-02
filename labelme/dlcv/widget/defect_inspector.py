"""缺陷巡检面板：按类别筛选缺陷并逐个放大定位。

缺陷通常很小，靠肉眼在整图上找标注点非常费时间。这里把所有标注按类别列出，
选中某个类别后可以一个个跳转并自动放大，方便复核是否标错。
"""

from __future__ import annotations

import os
from collections import Counter

from qtpy import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt

from labelme.dlcv import dlcv_tr
from labelme.dlcv.controller.zoom_controller import focus_shape
from labelme.dlcv.utils_func import ToastPreset
from labelme.dlcv.utils_func import notification
from labelme.utils.qt import newIcon


class DefectInspectorDock(QtWidgets.QDockWidget):
    """按类别查看当前图片缺陷的 Dock。"""

    REFRESH_DELAY_MS = 30

    def __init__(self, main_window, parent=None):
        super().__init__(dlcv_tr("缺陷巡检"), parent)
        self.main_window = main_window
        self._shapes = []
        self._category = None
        self._updating = False
        self._applying_visibility = False

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)

        self.setObjectName("defect_inspector_dock")
        self.setWindowIcon(newIcon("eye"))

        self._build_ui()
        self._connect_signals()
        self.refresh(reset_category=True)

    # region UI
    def _build_ui(self):
        main_widget = QtWidgets.QWidget(self)
        main_widget.setObjectName("defectInspectorPanel")
        layout = QtWidgets.QVBoxLayout(main_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        category_layout = QtWidgets.QHBoxLayout()
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(6)
        category_label = QtWidgets.QLabel(dlcv_tr("类别"), main_widget)
        category_label.setObjectName("defectFieldLabel")
        self.category_combo = QtWidgets.QComboBox(main_widget)
        self.category_combo.setObjectName("defectCategory")
        self.category_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.category_combo.setToolTip(
            dlcv_tr("按类别筛选当前图片的缺陷；选中后自动定位到该类第一个缺陷")
        )
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combo, 1)
        layout.addLayout(category_layout)

        self.summary_label = QtWidgets.QLabel(main_widget)
        self.summary_label.setObjectName("defectSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.defect_list = QtWidgets.QListWidget(main_widget)
        self.defect_list.setObjectName("defectList")
        self.defect_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )
        self.defect_list.setMinimumHeight(120)
        self.defect_list.setToolTip(
            dlcv_tr("点击缺陷可放大定位；Alt+←/→ 逐个切换，到首尾自动翻图")
        )
        layout.addWidget(self.defect_list, 1)

        nav_layout = QtWidgets.QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        self.prev_btn = QtWidgets.QPushButton(main_widget)
        self.prev_btn.setObjectName("defectNavBtn")
        self.prev_btn.setIcon(newIcon("prev"))
        self.prev_btn.setToolTip(dlcv_tr("上一个缺陷 (Alt+←)"))
        self.position_label = QtWidgets.QLabel("0/0", main_widget)
        self.position_label.setObjectName("defectPosition")
        self.position_label.setAlignment(Qt.AlignCenter)
        self.next_btn = QtWidgets.QPushButton(main_widget)
        self.next_btn.setObjectName("defectNavBtn")
        self.next_btn.setIcon(newIcon("next"))
        self.next_btn.setToolTip(dlcv_tr("下一个缺陷 (Alt+→)"))
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addSpacing(10)
        nav_layout.addWidget(self.position_label)
        nav_layout.addStretch(1)
        layout.addLayout(nav_layout)

        options_layout = QtWidgets.QHBoxLayout()
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(10)
        self.show_only_checkbox = QtWidgets.QCheckBox(
            dlcv_tr("画布只看当前类别"), main_widget
        )
        self.show_only_checkbox.setObjectName("defectFilterCheck")
        self.show_only_checkbox.setChecked(False)
        self.show_only_checkbox.setToolTip(
            dlcv_tr(
                "开启后画布只显示当前类别的标注，其他类别暂时隐藏；只影响显示，"
                "不修改标注。适合放大复核某一类缺陷，需要对比其他类别时关闭。"
            )
        )
        self.auto_zoom_checkbox = QtWidgets.QCheckBox(
            dlcv_tr("自动放大定位"), main_widget
        )
        self.auto_zoom_checkbox.setObjectName("defectFilterCheck")
        self.auto_zoom_checkbox.setChecked(True)
        self.auto_zoom_checkbox.setToolTip(
            dlcv_tr("跳转到缺陷时自动放大并居中显示；标签名称过大时按 C 隐藏")
        )
        options_layout.addWidget(self.show_only_checkbox)
        options_layout.addWidget(self.auto_zoom_checkbox)
        options_layout.addStretch(1)
        layout.addLayout(options_layout)

        self.setWidget(main_widget)
    # endregion

    # region 信号
    def _connect_signals(self):
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        self.defect_list.currentRowChanged.connect(self._on_row_changed)
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        self.next_btn.clicked.connect(lambda: self.step(1))
        self.show_only_checkbox.toggled.connect(
            lambda checked: self._apply_visibility()
        )

        window = self.main_window
        window.labelList.itemChanged.connect(self._on_label_item_changed)
        model = window.labelList.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(self._schedule_refresh)
        window.canvas.selectionChanged.connect(self._on_canvas_selection_changed)

        self.prev_action = QtWidgets.QAction(dlcv_tr("上一个缺陷"), window)
        self.prev_action.setShortcut("Alt+Left")
        self.prev_action.triggered.connect(lambda: self._shortcut_step(-1))
        window.addAction(self.prev_action)

        self.next_action = QtWidgets.QAction(dlcv_tr("下一个缺陷"), window)
        self.next_action.setShortcut("Alt+Right")
        self.next_action.triggered.connect(lambda: self._shortcut_step(1))
        window.addAction(self.next_action)

    def _shortcut_step(self, delta):
        if self.isVisible():
            self.step(delta)

    def _on_label_item_changed(self, item=None):
        if self._updating or self._applying_visibility:
            return
        self._schedule_refresh()

    def _schedule_refresh(self, *args):
        if self._updating:
            return
        self._refresh_timer.start(self.REFRESH_DELAY_MS)

    def _on_canvas_selection_changed(self, selected_shapes):
        if self._updating or not selected_shapes or len(selected_shapes) != 1:
            return
        try:
            row = self._shapes.index(selected_shapes[0])
        except ValueError:
            return
        if row != self.defect_list.currentRow():
            self._set_row(row)
            self._update_controls()
    # endregion

    # region 数据刷新
    def refresh(self, reset_category=False):
        """按当前画布标注重建类别和缺陷列表。"""
        if self._updating:
            return

        shapes = [
            shape
            for shape in getattr(self.main_window.canvas, "shapes", [])
            if getattr(shape, "label", "")
        ]
        counts = Counter(shape.label for shape in shapes)

        category = None if reset_category else self._category
        self._category = category

        current_shape = self._current_shape()
        self._updating = True
        try:
            self._rebuild_categories(counts, len(shapes))
            self._shapes = self._filter_shapes(shapes)
            self._rebuild_list(current_shape)
            self._update_controls()
            self._apply_visibility()
        finally:
            self._updating = False

    def on_image_loaded(self):
        """切换图片后刷新；保留当前类别，方便连续复核同一类缺陷。"""
        self.refresh()

    def on_folder_changed(self):
        """切换到新文件夹时回到“全部缺陷”，并恢复全部显示。"""
        self._category = None
        blocker = QtCore.QSignalBlocker(self.show_only_checkbox)
        try:
            self.show_only_checkbox.setChecked(False)
        finally:
            del blocker

    def _filter_shapes(self, shapes):
        if self._category is None:
            return list(shapes)
        return [shape for shape in shapes if shape.label == self._category]

    def _rebuild_categories(self, counts, total):
        combo = self.category_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem(dlcv_tr("全部缺陷 ({count})").format(count=total), None)
            for label, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            ):
                combo.addItem(f"{label} ({count})", label)
            if self._category is None:
                combo.setCurrentIndex(0)
            else:
                index = combo.findData(self._category)
                if index < 0:
                    # 跨图巡检时当前类别可能在当前图片里没有缺陷，
                    # 仍保留类别项，避免筛选被静默清掉。
                    combo.addItem(f"{self._category} (0)", self._category)
                    index = combo.count() - 1
                combo.setCurrentIndex(index)
        finally:
            combo.blockSignals(False)
        combo.setEnabled(total > 0)

    def _rebuild_list(self, current_shape):
        list_widget = self.defect_list
        list_widget.blockSignals(True)
        try:
            list_widget.clear()
            for index, shape in enumerate(self._shapes):
                try:
                    rect = shape.boundingRect()
                except Exception:
                    rect = QtCore.QRectF()
                width = max(0, int(round(rect.width())))
                height = max(0, int(round(rect.height())))
                text = (
                    f"{index + 1}. {shape.label}    {width}×{height} px"
                )
                item = QtWidgets.QListWidgetItem(text)
                item.setData(Qt.UserRole, shape)
                tooltip_template = dlcv_tr(
                    "{label}  宽 {width} px，高 {height} px，中心 ({x}, {y})"
                )
                item.setToolTip(
                    tooltip_template.format(
                        label=shape.label,
                        width=width,
                        height=height,
                        x=int(round(rect.center().x())),
                        y=int(round(rect.center().y())),
                    )
                )
                list_widget.addItem(item)

            if current_shape is not None:
                try:
                    row = self._shapes.index(current_shape)
                except ValueError:
                    row = -1
                if row >= 0:
                    list_widget.setCurrentRow(row)
        finally:
            list_widget.blockSignals(False)

    def _update_controls(self):
        count = len(self._shapes)
        row = self.defect_list.currentRow()
        if 0 <= row < count:
            self.position_label.setText(f"{row + 1}/{count}")
        else:
            self.position_label.setText(f"0/{count}")

        self.defect_list.setEnabled(count > 0)

        # 有文件夹时可跨图翻页；即使当前类别没有缺陷也要能点击。
        has_folder = bool(getattr(self.main_window, "lastOpenDir", None))
        has_image = bool(getattr(self.main_window, "filename", None))
        nav_enabled = has_folder and has_image
        self.prev_btn.setEnabled(nav_enabled)
        self.next_btn.setEnabled(nav_enabled)

        active_category = self._current_visible_category()
        if active_category is None:
            self.show_only_checkbox.setToolTip(
                dlcv_tr(
                    "全部缺陷默认显示全部；选中一条缺陷后勾选，可按该缺陷的类别过滤画布"
                )
            )
        elif self._category is None:
            self.show_only_checkbox.setToolTip(
                dlcv_tr(
                    "勾选后按当前选中缺陷的类别过滤画布；"
                    "只影响显示，不修改标注"
                )
            )
        else:
            self.show_only_checkbox.setToolTip(
                dlcv_tr(
                    "开启后画布只显示当前类别的标注，其他类别暂时隐藏；只影响显示，"
                    "不修改标注。适合放大复核某一类缺陷，需要对比其他类别时关闭。"
                )
            )

        total = len(self.main_window.canvas.shapes)
        categories = len({shape.label for shape in self.main_window.canvas.shapes})
        if total <= 0:
            self.summary_label.setText(dlcv_tr("当前图片暂无缺陷"))
        elif self._category is not None and not self._shapes:
            self.summary_label.setText(
                dlcv_tr("当前图片没有『{category}』缺陷，共 {count} 个缺陷").format(
                    category=self._category, count=total
                )
            )
        else:
            self.summary_label.setText(
                dlcv_tr("当前图片共 {count} 个缺陷，{categories} 类").format(
                    count=total, categories=categories
                )
            )

    def _current_shape(self):
        row = self.defect_list.currentRow()
        if 0 <= row < len(self._shapes):
            return self._shapes[row]
        return None

    def _current_visible_category(self):
        """当前用于画布过滤的类别。

        类别下拉选中具体类别时用它；选的是“全部缺陷”时，取缺陷列表当前
        选中缺陷的类别，这样在全部模式下选中某条缺陷也能只看它的类别。
        """
        if self._category is not None:
            return self._category
        shape = self._current_shape()
        return shape.label if shape is not None else None
    # endregion

    # region 跳转
    def _on_category_changed(self, index):
        if self._updating:
            return
        self._category = self.category_combo.itemData(index) if index >= 0 else None
        # “全部缺陷”就是全部显示；选中具体类别时默认只看该类。
        blocker = QtCore.QSignalBlocker(self.show_only_checkbox)
        try:
            self.show_only_checkbox.setChecked(self._category is not None)
        finally:
            del blocker
        shapes = [
            shape
            for shape in getattr(self.main_window.canvas, "shapes", [])
            if getattr(shape, "label", "")
        ]
        self._shapes = self._filter_shapes(shapes)

        self._updating = True
        try:
            self._rebuild_list(None)
            self._update_controls()
            self._apply_visibility()
        finally:
            self._updating = False

        if self._category is not None and self._shapes:
            # 指定类别时直接跳到第一个缺陷，省去再点一次列表。
            self._jump(0)
        else:
            self._update_controls()

    def _on_row_changed(self, row):
        if self._updating:
            return
        if 0 <= row < len(self._shapes):
            self._jump(row)
        else:
            self._update_controls()

    def step(self, delta):
        """在缺陷列表内前后跳转；越过首尾时自动切换上/下一张图片。"""
        if not self.main_window.filename:
            return

        count = len(self._shapes)
        if count <= 0:
            self._switch_image(delta)
            return

        row = self.defect_list.currentRow()
        if row < 0:
            self._jump(0 if delta > 0 else count - 1)
            return

        next_row = row + delta
        if 0 <= next_row < count:
            self._jump(next_row)
            return

        self._switch_image(delta)

    def _switch_image(self, delta):
        """跳转到相邻图片，并在新图片里定位该类别的第一个/最后一个缺陷。"""
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

        if not self._shapes:
            self._notify_no_defect_in_image(delta)
            return

        self._jump(0 if delta > 0 else len(self._shapes) - 1)

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

    def _jump(self, row):
        if not 0 <= row < len(self._shapes):
            return
        self._set_row(row)
        self._update_controls()
        focus_shape(
            self.main_window,
            self._shapes[row],
            auto_zoom=self.auto_zoom_checkbox.isChecked(),
        )
        if self._category is None and self.show_only_checkbox.isChecked():
            # “全部缺陷”模式下，过滤类别跟随当前选中的缺陷。
            self._apply_visibility()

    def _set_row(self, row):
        blocker = QtCore.QSignalBlocker(self.defect_list)
        try:
            self.defect_list.setCurrentRow(row)
        finally:
            del blocker

    # endregion

    # region 显示过滤
    def _apply_visibility(self):
        """按当前类别隐藏/显示画布标注。"""
        if self._applying_visibility:
            return
        self._applying_visibility = True
        try:
            category = self._current_visible_category()
            filter_on = self.show_only_checkbox.isChecked() and category is not None
            for item in self.main_window.labelList:
                shape = item.shape()
                visible = not filter_on or (
                    shape is not None and shape.label == category
                )
                state = Qt.Checked if visible else Qt.Unchecked
                if item.checkState() != state:
                    item.setCheckState(state)
        finally:
            self._applying_visibility = False
        self.main_window.canvas.update()
    # endregion
