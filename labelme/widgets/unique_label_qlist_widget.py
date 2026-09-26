# -*- encoding: utf-8 -*-

import html

from qtpy import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt

from .escapable_qlist_widget import EscapableQListWidget


class UniqueLabelQListWidget(EscapableQListWidget):
    ITEM_COLOR_ROLE = Qt.UserRole + 2

    def mousePressEvent(self, event):
        super(UniqueLabelQListWidget, self).mousePressEvent(event)
        if not self.indexAt(event.pos()).isValid():
            self.clearSelection()

    def findItemByLabel(self, label):
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.UserRole) == label:
                return item

    def createItemFromLabel(self, label):
        if self.findItemByLabel(label):
            raise ValueError("Item for label '{}' already exists".format(label))

        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.UserRole, label)
        return item

    def setItemLabel(self, item, label, color=None):
        qlabel = QtWidgets.QLabel(self.viewport())

        if color is not None:
            item.setData(self.ITEM_COLOR_ROLE, color)

        if color is None:
            qlabel.setText("{}".format(label))
        else:
            qlabel.setText(
                '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                    html.escape(label), *color
                )
            )
        qlabel.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        qlabel.setContentsMargins(6, 3, 6, 3)

        # 安装事件过滤器
        qlabel.installEventFilter(self)
        qlabel.setProperty("item", item)

        qlabel.ensurePolished()
        item.setSizeHint(qlabel.sizeHint())

        self.setItemWidget(item, qlabel)

    def _refresh_item_sizes(self):
        for row in range(self.count()):
            item = self.item(row)
            label = self.itemWidget(item)
            if label is not None:
                label.ensurePolished()
                item.setSizeHint(label.sizeHint())
        self.doItemsLayout()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            QtCore.QTimer.singleShot(0, self._refresh_item_sizes)

    def eventFilter(self, obj, event):
        if (
            isinstance(obj, QtWidgets.QLabel)
            and event.type() == QtCore.QEvent.MouseButtonPress
        ):
            item = obj.property("item")
            if item:
                self.setCurrentItem(item)
                self.itemClicked.emit(item)
                return True
        return super().eventFilter(obj, event)
