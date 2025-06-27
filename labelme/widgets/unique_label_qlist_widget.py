# -*- encoding: utf-8 -*-

import html

from qtpy import QtWidgets
from qtpy.QtCore import Qt

from .escapable_qlist_widget import EscapableQListWidget


class UniqueLabelQListWidget(EscapableQListWidget):
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
        qlabel = QtWidgets.QLabel()
        if color is None:
            qlabel.setText("{}".format(label))
        else:
            qlabel.setText(
                '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                    html.escape(label), *color
                )
            )
        qlabel.setAlignment(Qt.AlignBottom)

        # 安装事件过滤器
        qlabel.installEventFilter(self)
        qlabel.setProperty("item", item)

        item.setSizeHint(qlabel.sizeHint())

        self.setItemWidget(item, qlabel)

    def eventFilter(self, obj, event):
        if isinstance(obj, QtWidgets.QLabel) and event.type() == event.MouseButtonPress:
            item = obj.property("item")
            if item:
                self.setCurrentItem(item)
                self.itemClicked.emit(item)
                return True
        return super().eventFilter(obj, event)
