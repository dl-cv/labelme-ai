"""标注保存设置的非交互组件验证。"""

from types import SimpleNamespace

import pytest
from qtpy import QtCore
from qtpy import QtWidgets

from labelme.config import get_config
from labelme.dlcv.store import STORE
from labelme.dlcv.widget.setting_dock import SettingDock


@pytest.fixture(autouse=True)
def isolated_main_window():
    try:
        previous = STORE.main_window
    except AssertionError:
        previous = None
    yield
    STORE.register_main_window(previous)


def make_dock():
    parent = QtWidgets.QMainWindow()
    parent.enableKeepPrevScale = lambda enabled: None
    STORE.register_main_window(parent)
    config = get_config()
    canvas = SimpleNamespace(createMode="polygon", update=lambda: None)
    dock = SettingDock(parent, config, canvas)
    return parent, dock, config


def test_external_json_setting_is_not_available(qapp):
    parent, dock, config = make_dock()
    try:
        assert [child.name() for child in dock.parameter.child("proj_setting").children()] == ["proj_type"]
        assert "save_external_json" not in config
        assert "save_external_json" not in dock.save_settings()
    finally:
        parent.close()
        parent.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("legacy_value", [False, True])
def test_legacy_external_json_setting_is_not_restored_or_persisted(qapp, tmp_path, legacy_value):
    parent, dock, config = make_dock()
    try:
        settings = QtCore.QSettings(
            str(tmp_path / "settings.ini"), QtCore.QSettings.IniFormat
        )
        settings.setValue("setting_store", {"save_external_json": legacy_value, "display_shape_label": True})
        settings.sync()
        dock.restore_settings(settings)
        assert [child.name() for child in dock.parameter.child("proj_setting").children()] == ["proj_type"]
        assert "save_external_json" not in config
        settings.setValue("setting_store", dock.save_settings())
        settings.sync()
        assert "save_external_json" not in settings.value("setting_store")
    finally:
        parent.close()
        parent.deleteLater()
        qapp.processEvents()


def test_legacy_settings_keep_existing_display_parameters(qapp, tmp_path):
    parent, dock, config = make_dock()
    try:
        settings = QtCore.QSettings(
            str(tmp_path / "legacy.ini"), QtCore.QSettings.IniFormat
        )
        settings.setValue("setting_store", {"display_shape_label": True})
        dock.restore_settings(settings)
        assert dock.parameter.child("other_setting", "display_shape_label").value() is True
        assert "save_external_json" not in dock.save_settings()
    finally:
        parent.close()
        parent.deleteLater()
        qapp.processEvents()
