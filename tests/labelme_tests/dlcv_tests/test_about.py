from types import SimpleNamespace

from qtpy import QtCore, QtWidgets


def test_help_menu_about_dialog_shows_runtime_version(monkeypatch):
    from labelme import __appname__, __version__
    from labelme.dlcv import app as app_module

    monkeypatch.setattr(app_module, "dlcv_tr", lambda text: text)
    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class AboutWindow(QtWidgets.QWidget):
        show_about_dialog = app_module.MainWindow.show_about_dialog

    window = AboutWindow()
    window.actions = SimpleNamespace()
    window.menus = SimpleNamespace(help=QtWidgets.QMenu(window))
    window.menus.help.addAction("使用文档")

    app_module.MainWindow._init_about_action(window)

    menu_actions = window.menus.help.actions()
    assert menu_actions[-2].isSeparator()
    assert menu_actions[-1] is window.actions.about
    assert window.actions.about.text() == "关于"

    window.actions.about.trigger()
    qt_app.processEvents()

    dialog = window._about_dialog
    version_label = dialog.findChild(QtWidgets.QLabel)
    assert dialog.windowTitle() == "关于"
    assert version_label.text() == f"{__appname__}\n版本：{__version__}"
    assert dialog.windowFlags() & QtCore.Qt.WindowTitleHint
    assert dialog.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint
    assert dialog.windowFlags() & QtCore.Qt.WindowCloseButtonHint

    dialog.close()
    window.close()
