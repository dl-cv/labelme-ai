"""直接使用 PyQtGraph 官方 HistogramLUTWidget，保留原始灰度统计。"""

import numpy as np
import pyqtgraph as pg
from qtpy import QtCore, QtWidgets


def histogram_heights(counts):
    """ImageJ 式单峰限高，只改变绘图副本，不改变原始像素计数。"""
    heights = counts.astype(np.float64)
    if heights.size > 1:
        mode = int(heights.argmax())
        second = np.partition(heights, -2)[-2]
        if second > 0 and heights[mode] > second * 2:
            heights[mode] = second * 1.5
    return heights


class _HistogramImageItem(pg.ImageItem):
    """向官方控件提供缓存的全像素统计，避免默认自动采样漏掉灰度极值。"""

    def __init__(self):
        super().__init__(axisOrder="row-major")
        self.histogram = (None, None)

    def getHistogram(self, *args, **kwargs):
        return self.histogram


class GrayHistogram(pg.HistogramLUTWidget):
    levelsEdited = QtCore.Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent=parent, background="k", orientation="horizontal",
                         gradientPosition="bottom")
        self.setMinimumWidth(300)
        self.setMinimumHeight(260)
        self.setMaximumHeight(360)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        # 官方横向控件默认限制绘图区高度为 152，这里释放以容纳更大的直方图。
        self.item.vb.setMaximumHeight(16777215)
        self.item.vb.setMinimumHeight(180)
        self.item.axis.setPen(pg.mkPen("#cccccc"))
        self.item.axis.setTextPen(pg.mkPen("#cccccc"))
        self.item.axis.enableAutoSIPrefix(False)
        # 当前功能只调黑白场，固定官方默认灰度 LUT，不提供额外的颜色编辑。
        self.item.gradient.setEnabled(False)
        self.item.gradient.setToolTip("固定黑白灰度；拖动直方图两端的箭头调整黑场和白场。")
        self.setToolTip("原图全部像素的线性直方图；拖动官方左右箭头调整黑场和白场。")
        self.source_image = _HistogramImageItem()
        self.item.setImageItem(self.source_image)
        self.item.sigLevelsChanged.connect(self._levels_changed)
        self.counts = None
        self.edges = None
        self.window = (0, 1)
        self._heights = None
        self._updating = False
        self._ceiling = 65535
        self.item.region.hide()

    def set_image(self, image):
        self._updating = True
        try:
            if image is None:
                self.counts = self.edges = self._heights = None
                self.source_image.histogram = (None, None)
                self.source_image.clear()
                self.item.plot.clear()
                self.item.region.hide()
                return
            counts = np.bincount(image.ravel(), minlength=np.iinfo(image.dtype).max + 1)
            occupied = np.flatnonzero(counts)
            low, high = int(occupied[0]), int(occupied[-1]) + 1
            self.counts, self.edges = np.histogram(
                np.arange(low, high), bins=min(256, high - low),
                range=(low, high), weights=counts[low:high],
            )
            self._heights = histogram_heights(self.counts)
            self.source_image.histogram = ((self.edges[:-1] + self.edges[1:]) / 2,
                                           self._heights)
            self._ceiling = int(np.iinfo(image.dtype).max)
            self.item.region.setBounds((0, self._ceiling))
            self.source_image.setImage(image, autoLevels=False, levels=self.window)
            self.item.setHistogramRange(low, high, padding=0.02)
            self.item.vb.setYRange(0, max(1.0, float(self._heights.max())), padding=0.03)
            self.item.region.show()
        finally:
            self._updating = False

    def set_window(self, minimum, maximum):
        self._updating = True
        try:
            self.window = (minimum, maximum)
            self.item.setLevels(minimum, maximum)
            self.source_image.setLevels(self.window)
        finally:
            self._updating = False

    def focus_window(self, minimum, maximum):
        """仅调整视野：显示窗两侧各留一倍窗宽，避免远端背景挤压主峰。"""
        if self.counts is None:
            return
        width = max(1, maximum - minimum)
        left = max(0, minimum - width)
        right = min(self._ceiling + 1, maximum + width)
        self.item.setHistogramRange(left, right, padding=0)
        centers = (self.edges[:-1] + self.edges[1:]) / 2
        visible = self._heights[(centers >= left) & (centers <= right)]
        peak = float(visible.max()) if visible.size else 1.0
        self.item.vb.setYRange(0, max(1.0, peak), padding=0.05)

    def _levels_changed(self):
        if self._updating or self.counts is None:
            return
        minimum, maximum = self.item.getLevels()
        low = max(0, min(int(round(minimum)), self._ceiling - 1))
        high = max(low + 1, min(int(round(maximum)), self._ceiling))
        if (low, high) != self.window:
            self.set_window(low, high)
            self.levelsEdited.emit(low, high)
