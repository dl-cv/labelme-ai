"""按标注类别筛选图片的筛选卡片。

结构：
- ``ImageFilterIndex``：纯数据层扫描结果，递归统计每个类别包含多少张图片，
  不依赖 Qt 窗口，方便单独测试。
- ``ImageFilterScanThread``：后台扫描线程，避免大目录（尤其是网盘/网络盘）
  阻塞主界面。
- ``ImageFilterPanel``：文件树面板内展开的“图像筛选”卡片，样式对齐文件树。

类别来源 = 当前文件夹递归扫描到的外部 JSON 类别 ∪ 当前文件夹 label.txt 中
已定义的类别（还没有图片的类别显示 0 张）。
"""

from __future__ import annotations

import locale
import os
import threading
import time
from collections import Counter
from pathlib import Path

from dlcv_core.image_annotations import load_annotation
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy.QtCore import Qt

from labelme.dlcv import dlcv_tr
from labelme.dlcv.ui_style import get_image_filter_qss

ACCENT_COLOR = "#2F6FED"

_FILTER_ICON_CACHE = {}
_CHECK_ICON_CACHE = {}
_EMPTY_LABELS = frozenset()


def image_key(path) -> str:
    """把图片/目录路径统一成可比较的 key（绝对路径 + normcase）。"""
    try:
        return os.path.normcase(Path(os.fspath(path)).absolute().as_posix())
    except (OSError, TypeError, ValueError):
        return ""


def _shape_labels(data) -> frozenset[str]:
    labels = set()
    for shape in data.get("shapes") or []:
        if not isinstance(shape, dict):
            continue
        label = shape.get("label")
        if isinstance(label, str) and label:
            labels.add(label)
    return frozenset(labels) if labels else _EMPTY_LABELS


def read_label_order(root_dir) -> list[str]:
    """读取当前项目 label.txt 中的类别顺序（用于筛选列表排序）。"""
    path = Path(root_dir) / "label.txt"
    try:
        if not path.is_file():
            return []
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            # 外部脚本生成的 label.txt 可能不是 UTF-8，退回系统编码再试一次。
            text = path.read_text(encoding=locale.getpreferredencoding(False))
    except (OSError, UnicodeError):
        return []
    order = []
    for line in text.splitlines():
        label = line.strip()
        if label and label not in order:
            order.append(label)
    return order


class ImageFilterIndex:
    """一次类别扫描的结果。"""

    def __init__(
        self,
        root_dir: str,
        categories: dict[str, int],
        image_labels: dict[str, frozenset[str]],
        unannotated_count: int,
        total_images: int,
        failed_count: int = 0,
        dir_error_count: int = 0,
    ):
        self.root_dir = root_dir
        self.root_key = image_key(root_dir)
        self.categories = categories
        self.image_labels = image_labels
        self.unannotated_count = unannotated_count
        self.total_images = total_images
        self.failed_count = failed_count
        self.dir_error_count = dir_error_count
        self._matched_directories = None
        self._matched_signature = None

    # ---------- 查询 ----------
    def labels_for(self, image_path) -> frozenset[str] | None:
        """返回图片包含的类别集合；扫描结果里没有的图片返回 None。"""
        return self.image_labels.get(image_key(image_path))

    def matched_directories(self, categories) -> set[str]:
        """返回“存在匹配图片”的所有目录 key（含中间目录），用于隐藏空文件夹。"""
        categories = frozenset(categories or ())
        signature = categories
        if (
            self._matched_directories is not None
            and self._matched_signature == signature
        ):
            return self._matched_directories

        matched = set()
        root_key = self.root_key
        for path, labels in self.image_labels.items():
            if not (categories and labels & categories):
                continue
            parent = os.path.dirname(path)
            while parent and parent != root_key:
                if parent in matched:
                    break
                if not self._is_below_root(parent):
                    break
                matched.add(parent)
                parent = os.path.dirname(parent)
        self._matched_directories = matched
        self._matched_signature = signature
        return matched

    def _is_below_root(self, key: str) -> bool:
        if not self.root_key:
            return False
        root = self.root_key.rstrip("\\/")
        return key.startswith(root + os.sep) or key.startswith(root + "/")

    # ---------- 构建 ----------
    @classmethod
    def build(
        cls,
        root_dir,
        get_json_path,
        image_extensions,
        label_order=(),
        cancel_check=None,
        progress=None,
    ) -> "ImageFilterIndex | None":
        """递归扫描 root_dir 下的图片，统计类别与未标注图片数量。

        Args:
            root_dir: 图片根目录。
            get_json_path: 图片路径 -> JSON 路径（兼容 2D/3D/2.5D）。
            image_extensions: 图片扩展名元组（与树一致，可带点或不带点）。
            label_order: label.txt 中定义的类别顺序。
            cancel_check: 无参回调，返回 True 时中止扫描（返回 None）。
            progress: 已扫描图片数量回调。
        """
        root_path = Path(root_dir).absolute()
        extensions = tuple(ext.lower() for ext in image_extensions or ())

        category_counter = Counter()
        image_labels = {}
        failed_count = 0
        dir_error_count = 0
        scanned = 0

        stack = [root_path]
        while stack:
            directory = stack.pop()
            try:
                entries = list(os.scandir(directory))
            except OSError:
                dir_error_count += 1
                continue

            file_names = {}
            sub_dirs = []
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        sub_dirs.append(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                file_names[entry.name.lower()] = entry.name

            directory_key = image_key(directory)
            for name in sorted(file_names.values()):
                lower_name = name.lower()
                if not extensions or not lower_name.endswith(extensions):
                    continue
                if cancel_check is not None and cancel_check():
                    return None

                image_path = f"{directory.as_posix()}/{name}"
                try:
                    json_path = cls._resolve_json_path(
                        image_path, get_json_path, file_names, directory_key
                    )
                except Exception:
                    failed_count += 1
                    json_path = None
                labels = _EMPTY_LABELS
                if json_path is not None:
                    try:
                        data = load_annotation(json_path)
                    except Exception:
                        failed_count += 1
                        data = None
                    if isinstance(data, dict):
                        labels = _shape_labels(data)

                image_labels[image_key(image_path)] = labels
                for label in labels:
                    category_counter[label] += 1
                scanned += 1
                if progress is not None:
                    progress(scanned)

            stack.extend(sub_dirs)

        ordered_categories: dict[str, int] = {}
        for label in label_order or ():
            if label and label not in ordered_categories:
                ordered_categories[label] = category_counter.get(label, 0)
        extras = [
            label for label in category_counter if label not in ordered_categories
        ]
        extras.sort(key=lambda label: (-category_counter[label], label))
        for label in extras:
            ordered_categories[label] = category_counter[label]

        unannotated = sum(1 for labels in image_labels.values() if not labels)
        return cls(
            root_dir=root_path.as_posix(),
            categories=ordered_categories,
            image_labels=image_labels,
            unannotated_count=unannotated,
            total_images=len(image_labels),
            failed_count=failed_count,
            dir_error_count=dir_error_count,
        )

    @staticmethod
    def _resolve_json_path(
        image_path: str, get_json_path, file_names, directory_key: str
    ):
        json_path = get_json_path(image_path)
        if not json_path:
            return None
        try:
            json_dir = image_key(Path(json_path).parent)
        except (OSError, TypeError, ValueError):
            return None
        if json_dir == directory_key:
            # 同目录：用 scandir 文件名集合判断，避免每张图一次 exists。
            if os.path.basename(json_path).lower() in file_names:
                return json_path
            return None
        return json_path if os.path.isfile(json_path) else None


class ImageFilterScanThread(QtCore.QThread):
    """后台执行 ``ImageFilterIndex.build``。"""

    PROGRESS_STEP = 25
    PROGRESS_INTERVAL = 0.2

    sig_progress = QtCore.Signal(int)
    sig_finished = QtCore.Signal(object)
    sig_failed = QtCore.Signal(str)

    def __init__(
        self,
        root_dir,
        get_json_path,
        image_extensions,
        label_order=(),
        parent=None,
    ):
        super().__init__(parent)
        self._root_dir = root_dir
        self._get_json_path = get_json_path
        self._image_extensions = image_extensions
        self._label_order = label_order
        self._cancel_event = threading.Event()
        self._last_reported = 0
        self._last_report_time = 0.0

    def cancel(self):
        self._cancel_event.set()

    def _report_progress(self, scanned: int):
        now = time.monotonic()
        if (
            scanned > 1
            and scanned - self._last_reported < self.PROGRESS_STEP
            and now - self._last_report_time < self.PROGRESS_INTERVAL
        ):
            return
        self._last_reported = scanned
        self._last_report_time = now
        self.sig_progress.emit(scanned)

    def run(self):
        try:
            index = ImageFilterIndex.build(
                self._root_dir,
                self._get_json_path,
                self._image_extensions,
                self._label_order,
                cancel_check=self._cancel_event.is_set,
                progress=self._report_progress,
            )
        except Exception as exc:  # pragma: no cover - 防御性兜底
            self.sig_failed.emit(str(exc))
            return
        if index is None:
            return
        self.sig_finished.emit(index)


def _filter_icon(active: bool, size: int = 16) -> QtGui.QIcon:
    key = (bool(active), int(size))
    cached = _FILTER_ICON_CACHE.get(key)
    if cached is not None:
        return cached

    color = QtGui.QColor(ACCENT_COLOR if active else "#4B5563")
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QtGui.QPainter(pm)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(color)
        pen.setWidthF(1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        s = float(size)
        path = QtGui.QPainterPath()
        path.moveTo(1.8, 3.0)
        path.lineTo(s - 1.8, 3.0)
        path.lineTo(s * 0.60, s * 0.56)
        path.lineTo(s * 0.60, s - 2.4)
        path.lineTo(s * 0.40, s - 2.4)
        path.lineTo(s * 0.40, s * 0.56)
        path.closeSubpath()
        painter.drawPath(path)
    finally:
        painter.end()

    icon = QtGui.QIcon(pm)
    _FILTER_ICON_CACHE[key] = icon
    return icon


def make_filter_icon(active: bool = False, size: int = 16) -> QtGui.QIcon:
    """文件树顶部“图像筛选”按钮用的漏斗图标。"""
    return _filter_icon(active, size)


def _check_icon(checked: bool, size: int = 18) -> QtGui.QIcon:
    key = (bool(checked), int(size))
    cached = _CHECK_ICON_CACHE.get(key)
    if cached is not None:
        return cached

    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QtGui.QPainter(pm)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        rect = QtCore.QRectF(1.0, 1.0, size - 2.0, size - 2.0)
        if checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QtGui.QColor(ACCENT_COLOR))
            painter.drawRoundedRect(rect, 4.0, 4.0)

            pen = QtGui.QPen(QtGui.QColor("#FFFFFF"))
            pen.setWidthF(2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            check = QtGui.QPainterPath()
            check.moveTo(size * 0.26, size * 0.52)
            check.lineTo(size * 0.44, size * 0.70)
            check.lineTo(size * 0.76, size * 0.32)
            painter.drawPath(check)
        else:
            pen = QtGui.QPen(QtGui.QColor("#D1D5DB"))
            pen.setWidthF(1.4)
            painter.setPen(pen)
            painter.setBrush(QtGui.QColor("#FFFFFF"))
            painter.drawRoundedRect(rect, 3.5, 3.5)
    finally:
        painter.end()

    icon = QtGui.QIcon(pm)
    _CHECK_ICON_CACHE[key] = icon
    return icon


def _close_icon(color: str = "#6B7280", size: int = 12) -> QtGui.QIcon:
    key = ("close", color, int(size))
    cached = _FILTER_ICON_CACHE.get(key)
    if cached is not None:
        return cached

    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QtGui.QPainter(pm)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(color))
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        pad = size * 0.25
        painter.drawLine(
            QtCore.QPointF(pad, pad), QtCore.QPointF(size - pad, size - pad)
        )
        painter.drawLine(
            QtCore.QPointF(size - pad, pad), QtCore.QPointF(pad, size - pad)
        )
    finally:
        painter.end()

    icon = QtGui.QIcon(pm)
    _FILTER_ICON_CACHE[key] = icon
    return icon


def _category_colors() -> dict[str, QtGui.QColor]:
    """只读快照：主窗口标签列表里已有的标签颜色（不创建新标签项）。"""
    colors = {}
    try:
        from labelme.dlcv.store import STORE

        uniq_list = getattr(STORE.main_window, "uniqLabelList", None)
        if uniq_list is None:
            return colors
        from labelme.widgets.unique_label_qlist_widget import UniqueLabelQListWidget

        color_role = UniqueLabelQListWidget.ITEM_COLOR_ROLE
        for row in range(uniq_list.count()):
            item = uniq_list.item(row)
            label = item.data(Qt.UserRole)
            rgb = item.data(color_role)
            if not label or rgb is None or len(rgb) < 3:
                continue
            colors[label] = QtGui.QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    except Exception:
        pass
    return colors


def _category_color(label, colors=None) -> QtGui.QColor:
    """优先跟随画布里的标签颜色，取不到时用固定主题色。"""
    if colors:
        color = colors.get(label)
        if color is not None:
            return color
    return QtGui.QColor("#8B5CF6")


class _ElidedLabel(QtWidgets.QLabel):
    """宽度不足时按右侧省略，保留完整文本用于 tooltip。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.PlainText)
        self._full_text = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        self.set_full_text(text)

    def set_full_text(self, text: str):
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._update_elided()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        metrics = self.fontMetrics()
        width = max(0, self.width() - 2)
        self.setText(metrics.elidedText(self._full_text, Qt.ElideRight, width))


class _FilterRow(QtWidgets.QWidget):
    """一行类别：勾选框 + 类别色点 + 名称 + 数量。"""

    toggled = QtCore.Signal()

    def __init__(self, label, count: int, color, parent=None):
        super().__init__(parent)
        self.setObjectName("imageFilterRow")
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.label = label
        self.count = int(count)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 8, 4)
        layout.setSpacing(8)

        self.check_btn = QtWidgets.QToolButton(self)
        self.check_btn.setObjectName("imageFilterCheck")
        self.check_btn.setCheckable(True)
        self.check_btn.setAutoRaise(True)
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.setFixedSize(18, 18)
        self.check_btn.setIconSize(QtCore.QSize(18, 18))
        self.check_btn.setIcon(_check_icon(False))
        layout.addWidget(self.check_btn)

        self.dot = QtWidgets.QLabel(self)
        self.dot.setFixedSize(8, 8)
        self.dot.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        dot_color = color or QtGui.QColor("#8B5CF6")
        self.dot.setStyleSheet(
            "background-color: %s; border-radius: 4px;" % dot_color.name()
        )
        layout.addWidget(self.dot)

        self.name_label = _ElidedLabel(str(label), self)
        self.name_label.setObjectName("imageFilterName")
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.name_label, 1)

        self.count_label = QtWidgets.QLabel(
            dlcv_tr("{count} 张").format(count=self.count), self
        )
        self.count_label.setObjectName("imageFilterCount")
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.count_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.count_label)

        self.check_btn.toggled.connect(self._on_toggled)
        self.setToolTip(str(label))

    def _on_toggled(self, checked: bool):
        self.check_btn.setIcon(_check_icon(checked))
        self._refresh_checked_style()
        self.toggled.emit()

    def _refresh_checked_style(self):
        checked = self.check_btn.isChecked()
        if self.property("checked") == checked:
            return
        self.setProperty("checked", checked)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def is_checked(self) -> bool:
        return self.check_btn.isChecked()

    def set_checked(self, checked: bool):
        if self.check_btn.isChecked() == bool(checked):
            return
        blocker = QtCore.QSignalBlocker(self.check_btn)
        self.check_btn.setChecked(bool(checked))
        self.check_btn.setIcon(_check_icon(checked))
        del blocker
        self._refresh_checked_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.check_btn.toggle()
            event.accept()
            return
        super().mousePressEvent(event)


class ImageFilterPanel(QtWidgets.QWidget):
    """文件树面板内展开的“图像筛选”卡片。"""

    sig_apply = QtCore.Signal(object)  # 选中类别集合
    sig_cancel = QtCore.Signal()
    sig_close = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imageFilterPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        # 组件自带样式：不依赖全局 modern QSS，原版 UI 下也有完整卡片外观。
        self.setStyleSheet(get_image_filter_qss())
        self.category_rows: dict[str, _FilterRow] = {}
        self._loading = False
        self._ready = False
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        icon_label = QtWidgets.QLabel(self)
        icon_label.setPixmap(make_filter_icon(False, 16).pixmap(16, 16))
        icon_label.setFixedSize(16, 16)
        header.addWidget(icon_label)

        title = QtWidgets.QLabel(dlcv_tr("图像筛选"), self)
        title.setObjectName("imageFilterTitle")
        header.addWidget(title)
        header.addStretch()

        self.close_btn = QtWidgets.QToolButton(self)
        self.close_btn.setObjectName("imageFilterCloseBtn")
        self.close_btn.setAutoRaise(True)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip(dlcv_tr("关闭"))
        self.close_btn.setIcon(_close_icon())
        self.close_btn.setIconSize(QtCore.QSize(12, 12))
        self.close_btn.setFixedSize(20, 20)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setObjectName("imageFilterScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rows_container = QtWidgets.QWidget()
        self._rows_container.setObjectName("imageFilterRows")
        self._rows_layout = QtWidgets.QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()
        self.scroll.setWidget(self._rows_container)
        layout.addWidget(self.scroll, 1)

        self.status_label = QtWidgets.QLabel("", self)
        self.status_label.setObjectName("imageFilterStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        self.cancel_btn = QtWidgets.QPushButton(dlcv_tr("取消筛选"), self)
        self.cancel_btn.setObjectName("imageFilterCancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn = QtWidgets.QPushButton(dlcv_tr("应用筛选"), self)
        self.apply_btn.setObjectName("imageFilterApply")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(self.cancel_btn, 1)
        buttons.addWidget(self.apply_btn, 1)
        layout.addLayout(buttons)

        self.cancel_btn.clicked.connect(self.sig_cancel)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        self.close_btn.clicked.connect(self.sig_close)

        self._set_ready(False)
        self.status_label.setText(
            dlcv_tr("正在统计类别…（已扫描 {count} 张图片）").format(count=0)
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.sig_close.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---------- 状态 ----------
    def is_loading(self) -> bool:
        return self._loading

    def is_ready(self) -> bool:
        return self._ready

    def _set_ready(self, ready: bool):
        self._ready = bool(ready)
        self.apply_btn.setEnabled(self._ready)
        self.scroll.setEnabled(self._ready)

    def set_loading(self, scanned: int = 0):
        self._loading = True
        self._set_ready(False)
        self.status_label.setText(
            dlcv_tr("正在统计类别…（已扫描 {count} 张图片）").format(count=scanned)
        )

    def update_loading_progress(self, scanned: int):
        if not self._loading:
            return
        self.status_label.setText(
            dlcv_tr("正在统计类别…（已扫描 {count} 张图片）").format(count=scanned)
        )

    def set_error(self, message: str):
        self._loading = False
        self._set_ready(False)
        self.status_label.setText(message)

    def show_message(self, message: str):
        self._loading = False
        self._set_ready(False)
        self.status_label.setText(message)

    def reset(self):
        self.category_rows.clear()
        self._loading = False
        self._set_ready(False)
        self._clear_rows()
        self.status_label.setText("")

    def set_index(
        self,
        index: ImageFilterIndex,
        selected_categories=(),
    ):
        """用扫描结果重建类别列表，并恢复当前已应用的筛选状态。"""
        self._loading = False
        selected = set(selected_categories or ())
        self._rebuild_rows(index, selected)
        self._set_ready(True)

        if index.total_images == 0:
            status = dlcv_tr("当前文件夹没有图片")
        else:
            status = dlcv_tr("共 {images} 张图片，{categories} 个类别").format(
                images=index.total_images,
                categories=len(index.categories),
            )
        if index.failed_count:
            status += dlcv_tr("（{failed} 个标注文件读取失败）").format(
                failed=index.failed_count
            )
        if index.dir_error_count:
            status += dlcv_tr("（{dirs} 个目录无法读取）").format(
                dirs=index.dir_error_count
            )
        self.status_label.setText(status)

    def _clear_rows(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild_rows(self, index: ImageFilterIndex, selected: set[str]):
        self.category_rows = {}
        self._clear_rows()

        self._rows_container.setUpdatesEnabled(False)
        try:
            colors = _category_colors()
            for label, count in index.categories.items():
                row = _FilterRow(label, count, _category_color(label, colors))
                row.set_checked(label in selected)
                self.category_rows[label] = row
                self._rows_layout.addWidget(row)
            self._rows_layout.addStretch()
        finally:
            self._rows_container.setUpdatesEnabled(True)

    # ---------- 交互 ----------
    def selected_categories(self) -> set[str]:
        return {
            label for label, row in self.category_rows.items() if row.is_checked()
        }

    def _on_apply_clicked(self):
        if not self._ready:
            return
        self.sig_apply.emit(self.selected_categories())
