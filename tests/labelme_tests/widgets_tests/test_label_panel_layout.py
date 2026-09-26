import pytest
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets

from labelme.dlcv.ui_theme_manager import UiThemeManager
from labelme.translate.zh_CN import translate_data
from labelme.widgets.unique_label_qlist_widget import UniqueLabelQListWidget


@pytest.fixture(autouse=True)
def restore_application_style(qapp):
    font = QtGui.QFont(qapp.font())
    sheet = qapp.styleSheet()
    style = qapp.style().objectName()
    yield
    qapp.setStyle(style)
    qapp.setStyleSheet(sheet)
    qapp.setFont(font)


@pytest.mark.parametrize("size", [8, 10, 14, 20])
def test_label_contents_fit_after_theme_and_font_change(qtbot, qapp, tmp_path, size):
    window = QtWidgets.QMainWindow()
    dock = QtWidgets.QDockWidget(window)
    dock.setObjectName("Label List")
    widget = UniqueLabelQListWidget()
    dock.setWidget(widget)
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    qtbot.addWidget(window)
    item = widget.createItemFromLabel("person")
    widget.addItem(item)
    widget.setItemLabel(item, "person", (255, 0, 0))
    manager = UiThemeManager(window, QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.IniFormat))
    manager.set_theme("modern", persist=False, notify=False)
    font = QtGui.QFont(qapp.font())
    font.setPointSize(size)
    qapp.setFont(font)
    manager.on_app_font_changed()
    window.resize(700, 300)
    window.show()
    label = widget.itemWidget(item)
    qtbot.waitUntil(lambda: label.contentsRect().height() >= label.fontMetrics().height())
    assert label.font().pointSize() == size


def test_label_translation_has_no_escape_instruction():
    translator = QtCore.QTranslator()
    assert translator.loadFromData(translate_data)
    assert translator.translate("MainWindow", "Label List") == "标签列表（单击标签后设置标注名称）"
    assert translator.translate(
        "MainWindow", "Select label to start annotating for it."
    ) == "选择标签类型并开始以其标注。"


@pytest.mark.parametrize("size", [8, 10, 14, 20])
def test_polygon_label_geometry_uses_current_font(qtbot, qapp, tmp_path, size):
    from labelme.widgets.label_list_widget import LabelListWidget, LabelListWidgetItem

    window = QtWidgets.QMainWindow()
    dock = QtWidgets.QDockWidget(window)
    dock.setObjectName("Labels")
    widget = LabelListWidget()
    dock.setWidget(widget)
    window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    qtbot.addWidget(window)
    widget.addItem(LabelListWidgetItem('person <font color="#ff0000">●</font>'))
    manager = UiThemeManager(window, QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.IniFormat))
    manager.set_theme("modern", persist=False, notify=False)
    font = QtGui.QFont(qapp.font())
    font.setPointSize(size)
    qapp.setFont(font)
    manager.on_app_font_changed()
    window.resize(700, 300)
    window.show()
    index = widget.model().index(0, 0)
    delegate = widget.itemDelegate()
    option = QtWidgets.QStyleOptionViewItem(widget.viewOptions())
    option.widget = widget
    expected = delegate.sizeHint(option, index)
    qtbot.waitUntil(lambda: widget.visualRect(index).height() >= expected.height())
    option.rect = widget.visualRect(index)
    delegate.initStyleOption(option, index)
    text_rect = delegate.textRect(option)
    assert delegate.doc.defaultFont().pointSize() == size
    assert text_rect.height() >= delegate.doc.size().height()
