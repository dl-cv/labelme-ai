from qtpy import QtCore
from qtpy import QtWidgets
from qtpy.QtCore import Qt


class EscapableQListWidget(QtWidgets.QListWidget):
    def event(self, event):
        if (
            event.type() == QtCore.QEvent.ShortcutOverride
            and event.key() == Qt.Key_Escape
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clearSelection()
            self.setCurrentRow(-1)
            event.accept()
            return
        super().keyPressEvent(event)
