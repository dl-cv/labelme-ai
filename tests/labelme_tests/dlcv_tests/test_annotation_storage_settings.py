"""标注保存设置的非交互组件验证。"""

from types import SimpleNamespace

import pytest
from qtpy import QtCore, QtWidgets

from labelme.config import get_config
from labelme.dlcv.widget.setting_dock import SettingDock
from labelme.dlcv.store import STORE


@pytest.fixture(scope="module")
def qt_app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_main_window():
    try:
        previous = STORE.main_window
    except AssertionError:
        previous = None
    yield
    STORE.register_main_window(previous)


def _make_dock():
    parent = QtWidgets.QMainWindow()
    parent.enableKeepPrevScale = lambda enabled: None
    STORE.register_main_window(parent)
    config = get_config()
    canvas = SimpleNamespace(createMode="polygon", update=lambda: None)
    dock = SettingDock(parent, config, canvas)
    return parent, dock, config


def test_external_json_is_enabled_by_default(qt_app):
    parent, dock, config = _make_dock()
    try:
        parameter = dock.parameter.child("proj_setting", "save_external_json")
        assert parameter.value() is True
        assert config["save_external_json"] is True
        assert dock.save_settings()["save_external_json"] is True
    finally:
        parent.close()
        parent.deleteLater()
        qt_app.processEvents()


def test_external_json_setting_updates_config_and_persists(qt_app, tmp_path):
    parent, dock, config = _make_dock()
    restored_parent, restored_dock, restored_config = _make_dock()
    try:
        dock.parameter.child("proj_setting", "save_external_json").setValue(False)
        assert config["save_external_json"] is False
        settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.IniFormat)
        settings.setValue("setting_store", dock.save_settings())
        settings.sync()
        restored_dock.restore_settings(settings)
        assert restored_config["save_external_json"] is False
        assert restored_dock.parameter.child("proj_setting", "save_external_json").value() is False
    finally:
        for window in [parent, restored_parent]:
            window.close()
            window.deleteLater()
        qt_app.processEvents()


def test_legacy_settings_enable_external_json_by_default(qt_app, tmp_path):
    parent, dock, config = _make_dock()
    try:
        settings = QtCore.QSettings(str(tmp_path / "legacy.ini"), QtCore.QSettings.IniFormat)
        settings.setValue("setting_store", {"display_shape_label": True})
        dock.restore_settings(settings)
        assert config["save_external_json"] is True
    finally:
        parent.close()
        parent.deleteLater()
        qt_app.processEvents()
