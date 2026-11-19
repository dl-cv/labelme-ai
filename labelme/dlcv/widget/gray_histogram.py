"""原始灰度直方图：缓存 NumPy 统计，调窗时只重绘标线。"""

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets


class GrayHistogram(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(145)
        self.setMaximumHeight(180)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setToolTip("统计原图全部像素，包含背景；纵轴为对数像素数。\n"
                        "橙线为黑场，蓝线为白场；阴影为当前显示范围。")
        self.counts = None
        self.edges = None
        self.window = (0, 1)
        self._heights = None

    def set_image(self, image):
        if image is None:
            self.counts = self.edges = self._heights = None
        else:
            counts = np.bincount(image.ravel(), minlength=np.iinfo(image.dtype).max + 1)
            occupied = np.flatnonzero(counts)
            low, high = int(occupied[0]), int(occupied[-1]) + 1
            # 只分箱绘图，不修改原始统计，也不使用调窗后的 8 位显示图。
            self.counts, self.edges = np.histogram(
                np.arange(low, high), bins=min(256, high - low),
                range=(low, high), weights=counts[low:high],
            )
            heights = np.log1p(self.counts.astype(np.float64))
            self._heights = heights / heights.max()
        self.update()

    def set_window(self, minimum, maximum):
        self.window = (minimum, maximum)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        area = QtCore.QRectF(10, 8, max(1, self.width() - 20), max(1, self.height() - 38))
        painter.setPen(palette.mid().color())
        painter.drawRect(area)
        if self.counts is None:
            painter.setPen(palette.text().color())
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "暂无灰度图像")
            return

        left, right = float(self.edges[0]), float(self.edges[-1])

        def x_position(value):
            fraction = np.clip((value - left) / (right - left), 0, 1)
            return area.left() + float(fraction) * area.width()

        low_x, high_x = (x_position(value) for value in self.window)
        shade = palette.highlight().color()
        shade.setAlpha(28)
        painter.fillRect(QtCore.QRectF(low_x, area.top(), high_x - low_x, area.height()), shade)
        path = QtGui.QPainterPath()
        path.moveTo(area.bottomLeft())
        for index, height in enumerate(self._heights):
            x1 = x_position(self.edges[index])
            x2 = x_position(self.edges[index + 1])
            y = area.bottom() - float(height) * area.height()
            path.lineTo(x1, y)
            path.lineTo(x2, y)
        path.lineTo(area.bottomRight())
        path.closeSubpath()
        painter.fillPath(path, palette.mid().color())

        for value, color in zip(self.window, ("#d97706", "#2563eb")):
            # 窗值在原图范围外时不伪装成边界内的标线。
            if left <= value <= right:
                painter.setPen(QtGui.QPen(QtGui.QColor(color), 2))
                x = x_position(value)
                painter.drawLine(QtCore.QPointF(x, area.top()), QtCore.QPointF(x, area.bottom()))
        painter.setPen(palette.text().color())
        label_y = area.bottom() + 4
        labels = (str(int(left)), str(int((left + right - 1) / 2)), str(int(right - 1)))
        for index, text in enumerate(labels):
            rect = QtCore.QRectF(area.left() + index * area.width() / 3, label_y,
                                 area.width() / 3, 25)
            alignment = (QtCore.Qt.AlignLeft, QtCore.Qt.AlignHCenter, QtCore.Qt.AlignRight)[index]
            painter.drawText(rect, alignment | QtCore.Qt.AlignTop, text)
