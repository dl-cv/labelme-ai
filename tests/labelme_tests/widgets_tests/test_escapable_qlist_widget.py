import pytest
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets

from labelme.widgets.escapable_qlist_widget import EscapableQListWidget
from labelme.widgets.unique_label_qlist_widget import UniqueLabelQListWidget


@pytest.mark.gui
def test_escape_clears_selection_before_window_shortcut(qtbot):
    window = QtWidgets.QMainWindow()
    widget = EscapableQListWidget(window)
    widget.addItems(["cat", "dog"])
    window.setCentralWidget(widget)

    shortcut_triggered = []
    action = QtWidgets.QAction(window)
    action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape))
    action.triggered.connect(lambda: shortcut_triggered.append(True))
    window.addAction(action)

    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    widget.setCurrentRow(0)
    widget.setFocus()

    qtbot.keyClick(widget, QtCore.Qt.Key_Escape)

    assert widget.selectedItems() == []
    assert widget.currentRow() == -1
    assert shortcut_triggered == []


@pytest.mark.gui
def test_unique_label_item_has_readable_vertical_spacing(qtbot):
    widget = UniqueLabelQListWidget()
    qtbot.addWidget(widget)

    item = widget.createItemFromLabel("标签")
    widget.addItem(item)
    widget.setItemLabel(item, "标签", (255, 0, 0))

    assert item.sizeHint().height() >= widget.fontMetrics().height() + 6
