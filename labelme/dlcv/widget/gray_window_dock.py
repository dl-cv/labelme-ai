"""原始整数灰度的显示窗；仅生成显示副本，不修改输入像素。"""

import numpy as np
from qtpy import QtCore, QtWidgets

from labelme.dlcv.widget.gray_histogram import GrayHistogram


def auto_window(image):
    """优先拉伸紧凑的工件主峰；没有明显主峰时使用前景百分位。"""
    counts = np.bincount(image.ravel(), minlength=np.iinfo(image.dtype).max + 1)
    foreground = counts.copy()
    foreground[foreground > image.size * 0.1] = 0
    if not foreground.any():
        foreground = counts
    cumulative = foreground.cumsum()
    total = cumulative[-1]
    high = int(np.searchsorted(cumulative, total * 0.995))
    # 百分位会把工件边缘的长尾也纳入窗口，窄灰度细节仍几乎不可见。
    # 在去除平坦背景后的直方图中找显著主峰，不把某批图的灰度值写死。
    occupied = np.flatnonzero(foreground)
    start, end = int(occupied[0]), int(occupied[-1]) + 1
    bins = min(1024, end - start)
    histogram, edges = np.histogram(
        np.arange(start, end), bins=bins, range=(start, end),
        weights=foreground[start:end],
    )
    smooth = np.convolve(histogram, np.array([1, 4, 6, 4, 1]) / 16, mode="same")
    peak = int(smooth.argmax())
    if bins >= 16 and smooth[peak] > smooth.mean() * 5:
        left = right = peak
        threshold = smooth[peak] * 0.2
        while left > 0 and smooth[left - 1] >= threshold:
            left -= 1
        while right < bins - 1 and smooth[right + 1] >= threshold:
            right += 1
        if 2 <= right - left + 1 < bins / 2:
            high = int(np.ceil(edges[right + 1]))
    # 黑场取排除背景后的真实最小值，不加偏移，也不裁掉低分位像素。
    low = start
    if low >= high:
        low = min(low, np.iinfo(image.dtype).max - 1)
        high = low + 1
    return int(low), int(high)


def window_to_uint8(image, minimum, maximum):
    if maximum <= minimum:
        raise ValueError("显示最大值必须大于最小值")
    # 查找表避免在每次拖动时分配全尺寸浮点图，也避免 uint16 减法溢出。
    levels = np.arange(np.iinfo(image.dtype).max + 1, dtype=np.float64)
    table = np.clip((levels - minimum) * (255.0 / (maximum - minimum)), 0, 255)
    return table.astype(np.uint8)[image]


class GrayWindowDock(QtWidgets.QDockWidget):
    imageChanged = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__("灰度显示调整", parent)
        self.setObjectName("gray_window_dock")
        self.raw_image = None
        self._window = (0, 1)
        self._slider_range = (0, 65535)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._emit_image)

        panel = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(panel)
        histogram_title = QtWidgets.QLabel("原图灰度直方图（像素数为对数）\n橙线：黑场 · 蓝线：白场")
        histogram_title.setWordWrap(True)
        layout.addWidget(histogram_title)
        self.histogram = GrayHistogram(panel)
        layout.addWidget(self.histogram)
        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.controls = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        self.minimum_spin, self.minimum_slider = self._add_row(controls_layout, "最小值（黑场）")
        self.maximum_spin, self.maximum_slider = self._add_row(controls_layout, "最大值（白场）")
        self.minimum_spin.valueChanged.connect(self._minimum_changed)
        self.maximum_spin.valueChanged.connect(self._maximum_changed)
        buttons = QtWidgets.QHBoxLayout()
        self.auto_button = QtWidgets.QPushButton("自动调整")
        self.reset_button = QtWidgets.QPushButton("重置")
        self.auto_button.clicked.connect(self.auto_adjust)
        self.reset_button.clicked.connect(self.reset_window)
        buttons.addWidget(self.auto_button)
        buttons.addWidget(self.reset_button)
        controls_layout.addLayout(buttons)
        layout.addWidget(self.controls)
        note = QtWidgets.QLabel("仅调整显示，不修改原图和标注。\n自动黑场 = 排除背景后的最小灰度；白场按工件主峰计算，可继续微调。\n滑块覆盖原图灰度范围；输入框和上下箭头可精调，重置恢复完整灰度范围。")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.setWidget(panel)
        self.set_image(None)

    @staticmethod
    def _add_row(layout, title):
        layout.addWidget(QtWidgets.QLabel(title))
        row = QtWidgets.QHBoxLayout()
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        spin = QtWidgets.QSpinBox()
        spin.setKeyboardTracking(False)
        spin.setMinimumWidth(85)
        slider.valueChanged.connect(spin.setValue)
        # 反向同步由 _set_window 完成，避免精细滑块把手输值截断。
        row.addWidget(slider, 1)
        row.addWidget(spin)
        layout.addLayout(row)
        return spin, slider

    def set_image(self, image):
        self._timer.stop()
        supported = (image is not None and image.ndim == 2
                     and image.dtype in (np.dtype("uint8"), np.dtype("uint16")))
        self.raw_image = image if supported else None
        self.histogram.set_image(self.raw_image)
        self.controls.setEnabled(supported)
        if not supported:
            self.info.setText("打开 8 位或 16 位灰度图后可调整原始灰度显示范围。")
            return None
        self.info.setText(f"{image.dtype.itemsize * 8} 位灰度 · 原始范围：{image.min()}～{image.max()}")
        ceiling = int(np.iinfo(image.dtype).max)
        widgets = (self.minimum_spin, self.maximum_spin,
                   self.minimum_slider, self.maximum_slider)
        blockers = [QtCore.QSignalBlocker(widget) for widget in widgets]
        for widget in widgets:
            widget.setRange(0, ceiling)
        del blockers
        low, high = auto_window(image) if image.dtype == np.uint16 else (0, ceiling)
        self._reset_slider_range(low, high)
        self._set_window(low, high, emit=False)
        return self.display_image()

    def _reset_slider_range(self, low, high):
        # 自动窗只决定初始黑白场，不能限制可调范围。
        self._slider_range = (min(int(self.raw_image.min()), low),
                              max(int(self.raw_image.max()), high))

    def _set_window(self, low, high, emit=True):
        widgets = (self.minimum_spin, self.maximum_spin,
                   self.minimum_slider, self.maximum_slider)
        blockers = [QtCore.QSignalBlocker(widget) for widget in widgets]
        range_low, range_high = self._slider_range
        self._slider_range = (min(range_low, low), max(range_high, high))
        for slider in (self.minimum_slider, self.maximum_slider):
            slider.setRange(*self._slider_range)
            slider.setPageStep(max(1, (high - low) // 20))
            slider.setToolTip(f"滑块范围：{self._slider_range[0]}～{self._slider_range[1]}；"
                              "输入框支持完整位深范围，上下箭头可按 1 灰度级精调。")
        self._window = (low, high)
        self.histogram.set_window(low, high)
        for widget, value in zip(widgets, (low, high, low, high)):
            widget.setValue(value)
        del blockers
        if emit:
            self._timer.stop()
            self._emit_image()

    def _minimum_changed(self, value):
        if self.raw_image is None:
            return
        ceiling = self.maximum_spin.maximum()
        old_low, old_high = self._window
        low = min(value, ceiling - 1)
        high = old_high
        if low >= high:
            high = min(ceiling, low + old_high - old_low)
            low = high - (old_high - old_low)
        self._set_window(low, high, emit=False)
        self._timer.start()

    def _maximum_changed(self, value):
        if self.raw_image is None:
            return
        old_low, old_high = self._window
        high = max(1, value)
        low = old_low
        if high <= low:
            low = max(0, high - (old_high - old_low))
            high = low + old_high - old_low
        self._set_window(low, high, emit=False)
        self._timer.start()

    def display_image(self):
        if self.raw_image is None:
            return None
        return window_to_uint8(self.raw_image, self.minimum_spin.value(), self.maximum_spin.value())

    def _emit_image(self):
        image = self.display_image()
        if image is not None:
            self.imageChanged.emit(image)

    def auto_adjust(self):
        if self.raw_image is not None:
            low, high = auto_window(self.raw_image)
            self._reset_slider_range(low, high)
            self._set_window(low, high)

    def reset_window(self):
        if self.raw_image is not None:
            ceiling = int(np.iinfo(self.raw_image.dtype).max)
            self._slider_range = (0, ceiling)
            self._set_window(0, ceiling)
