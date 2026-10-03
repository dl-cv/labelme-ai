"""测试设置与用户目录隔离，使用实际模块执行检查。"""

import pytest
from pyqttoast import Toast
from qtpy import QtCore


@pytest.fixture(autouse=True)
def isolated_user_settings(monkeypatch, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("user-settings")
    for name in (
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
    ):
        path = tmp_path / name.lower()
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    previous_format = QtCore.QSettings.defaultFormat()
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
    for scope in (QtCore.QSettings.UserScope, QtCore.QSettings.SystemScope):
        QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, scope, str(tmp_path))
    yield
    Toast.reset()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    QtCore.QSettings.setDefaultFormat(previous_format)
