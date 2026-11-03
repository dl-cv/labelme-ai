"""把画布缩放并居中到指定标注。

缺陷巡检面板点击某个缺陷时，画布需要立即放大到能看清缺陷细节的程度，
而不是让用户自己滚轮放大再拖动找位置。
"""

from __future__ import annotations

from qtpy import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt

DEFAULT_VIEWPORT_FRACTION = 0.5


def _scroll_area(window):
    """定位画布所在的滚动区域（兼容被 QSplitter 包裹的中央控件）。"""
    scroll_bars = getattr(window, "scrollBars", None) or {}
    bar = scroll_bars.get(Qt.Horizontal) or scroll_bars.get(Qt.Vertical)
    if bar is not None:
        parent = bar.parentWidget()
        if parent is not None and hasattr(parent, "viewport"):
            return parent

    central = window.centralWidget()
    if central is not None and hasattr(central, "viewport"):
        return central
    if central is not None:
        areas = central.findChildren(QtWidgets.QAbstractScrollArea)
        for area in areas:
            if getattr(area, "viewport", None) is not None:
                return area
    return None


def _viewport_size(window):
    """返回滚动区域的可视尺寸（窗口未显示时给一个稳定兜底值）。"""
    width = height = 0
    canvas = getattr(window, "canvas", None)
    viewport = canvas.parentWidget() if canvas is not None else None
    if viewport is not None:
        width = viewport.width()
        height = viewport.height()

    if width < 200 or height < 150:
        scroll_area = _scroll_area(window)
        if scroll_area is not None:
            area_viewport = scroll_area.viewport()
            width = max(width, area_viewport.width())
            height = max(height, area_viewport.height())

    if width < 200 or height < 150:
        width = max(width, window.width() - 80)
        height = max(height, window.height() - 120)
    if width < 200 or height < 150:
        width, height = 1200, 800
    return width, height


def zoom_to_shape(window, shape, viewport_fraction=DEFAULT_VIEWPORT_FRACTION) -> bool:
    """缩放到指定标注并把它放在视口中心，返回是否成功。"""
    if window is None or shape is None:
        return False

    canvas = getattr(window, "canvas", None)
    pixmap = getattr(canvas, "pixmap", None)
    if pixmap is None or pixmap.isNull():
        return False

    try:
        rect = shape.boundingRect()
    except Exception:
        rect = QtCore.QRectF()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        points = getattr(shape, "points", None) or []
        if not points:
            return False
        rect = QtCore.QRectF(points[0], points[0])

    view_w, view_h = _viewport_size(window)
    pix_w = max(1, pixmap.width())
    pix_h = max(1, pixmap.height())

    fit_scale = min(view_w / pix_w, view_h / pix_h)
    shape_extent = max(1.0, rect.width(), rect.height())
    target_scale = min(view_w, view_h) * float(viewport_fraction) / shape_extent

    max_zoom = 5.0
    zoom_widget = getattr(window, "zoomWidget", None)
    if zoom_widget is not None:
        max_zoom = max(1.0, zoom_widget.maximum() / 100.0)
    scale = max(fit_scale, min(target_scale, max_zoom))
    zoom_value = max(1, int(round(scale * 100)))

    window.setZoom(zoom_value)
    scale = canvas.scale
    if scale <= 0:
        return False

    # 先把画布偏移归零，用滚动条把标注中心滚动到视口中心，
    # 再用画布偏移补偿滚动条被夹紧（图片小于视口/靠近边缘）的差值。
    canvas.offset = QtCore.QPointF(0, 0)
    offset_center = canvas.offsetToCenter()
    center = rect.center()

    window.setScroll(
        Qt.Horizontal,
        (center.x() + offset_center.x()) * scale - view_w / 2.0,
    )
    window.setScroll(
        Qt.Vertical,
        (center.y() + offset_center.y()) * scale - view_h / 2.0,
    )

    scroll_bars = window.scrollBars
    h_value = scroll_bars[Qt.Horizontal].value()
    v_value = scroll_bars[Qt.Vertical].value()
    canvas.offset = QtCore.QPointF(
        (h_value + view_w / 2.0) / scale - center.x() - offset_center.x(),
        (v_value + view_h / 2.0) / scale - center.y() - offset_center.y(),
    )
    canvas.update()
    return True


def focus_shape(window, shape, auto_zoom=True) -> bool:
    """选中标注；auto_zoom 时同时放大定位到该标注。"""
    if window is None or shape is None:
        return False

    canvas = window.canvas
    canvas.selectShapes([shape])
    if auto_zoom:
        return zoom_to_shape(window, shape)
    return True
