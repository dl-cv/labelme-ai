"""多边形标签列表的显示文本：标签名 + 宽×高 + 颜色点。"""

from __future__ import annotations

import html

from qtpy import QtCore


def label_item_html(shape):
    text = html.escape(shape.label)
    if shape.group_id is not None:
        text = "{} ({})".format(text, html.escape(str(shape.group_id)))
    try:
        rect = shape.boundingRect()
    except Exception:
        rect = QtCore.QRectF()
    width = max(0, int(round(rect.width())))
    height = max(0, int(round(rect.height())))
    r, g, b = shape.fill_color.getRgb()[:3]
    return '{}  {}×{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
        text, width, height, r, g, b
    )


def update_latest_label_item_text(window, shape):
    if not len(window.labelList):
        return
    item = window.labelList[len(window.labelList) - 1]
    if item.shape() is shape:
        item.setText(label_item_html(shape))


def refresh_label_item_text(window, shape):
    if shape is None:
        return
    try:
        item = window.labelList.findItemByShape(shape)
    except ValueError:
        return
    item.setText(label_item_html(shape))


def refresh_selected_label_item_texts(window):
    for shape in window.canvas.selectedShapes:
        refresh_label_item_text(window, shape)


class LabelItemTextMixin:
    """在原有 addLabel / _update_item / shapeMoved 流程后同步尺寸文本。"""

    def addLabel(self, shape):
        super().addLabel(shape)
        update_latest_label_item_text(self, shape)
        sync = getattr(self, "_sync_label_dialog_order_with_uniq_list", None)
        if sync is not None:
            sync()

    def _update_item(self, item, text, flags, group_id, description):
        super()._update_item(item, text, flags, group_id, description)
        shape = item.shape() if item is not None else None
        if shape is not None:
            item.setText(label_item_html(shape))

    def _on_canvas_shape_moved(self):
        refresh_selected_label_item_texts(self)
        self.refresh_invalid_polygon_state()
