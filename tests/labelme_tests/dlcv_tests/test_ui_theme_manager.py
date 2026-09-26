from unittest import mock

import pytest
from qtpy import QtCore
from qtpy import QtWidgets

from labelme.dlcv.dlcv_translator import dlcv_tr
from labelme.dlcv.ui_theme_manager import UiThemeManager


@pytest.fixture
def theme_manager(qtbot, tmp_path):
    window = QtWidgets.QMainWindow()
    qtbot.addWidget(window)
    settings = QtCore.QSettings(
        str(tmp_path / "settings.ini"), QtCore.QSettings.IniFormat
    )
    settings.clear()
    return UiThemeManager(window, settings), settings


def test_default_theme_is_modern(theme_manager):
    manager, settings = theme_manager

    assert settings.value("ui/theme") is None
    assert manager.get_saved_theme() == manager.THEME_MODERN

    manager.set_theme = mock.Mock()
    manager.apply_from_settings()
    manager.set_theme.assert_called_once_with(
        manager.THEME_MODERN, persist=False, notify=False
    )


def test_saved_native_theme_is_preserved(theme_manager):
    manager, settings = theme_manager
    settings.setValue("ui/theme", manager.THEME_CLASSIC)

    assert manager.get_saved_theme() == manager.THEME_CLASSIC


def test_theme_menu_uses_native_name(theme_manager):
    manager, _ = theme_manager
    menu = QtWidgets.QMenu()
    old_lang = dlcv_tr.get_lang()
    dlcv_tr.set_lang("zh_CN")
    try:
        theme_menu = manager.install_to_setting_menu(menu)
        assert [action.text() for action in theme_menu.actions()] == [
            "新版UI（现代）",
            "原版UI（原生）",
        ]
    finally:
        dlcv_tr.set_lang(old_lang)


def test_modern_titles_are_created_before_window_is_shown(theme_manager):
    manager, _ = theme_manager
    dock = QtWidgets.QDockWidget("设置面板", manager.main_window)
    dock.setWidget(QtWidgets.QListWidget())
    manager.main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
    assert not dock.isVisible()
    manager._apply_modern_dock_title_bars(True)
    title = dock.titleBarWidget()
    assert title is not None
    label = title.findChild(QtWidgets.QLabel, "dlcvDockTitleLabel")
    assert label.text() == "设置面板"
    assert title.height() >= label.fontMetrics().height() + 6
    manager._apply_modern_dock_title_bars(False)
    assert dock.titleBarWidget() is None
