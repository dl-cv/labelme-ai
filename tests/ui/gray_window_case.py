"""在隔离桌面中展示真实 TIFF 的灰度窗面板，供 python_sample.py 采集。"""
import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets

from labelme import __appname__
from labelme.config import get_config
from labelme.dlcv import dlcv_tr
from labelme.dlcv.app import MainWindow as AppMainWindow
from labelme.dlcv.store import STORE
from labelme.utils import newIcon


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filename", type=Path)
    parser.add_argument("--minimum", type=int)
    parser.add_argument("--maximum", type=int)
    options = parser.parse_args()
    original_hash = hashlib.sha256(options.filename.read_bytes()).digest()
    with tempfile.TemporaryDirectory(prefix="labelme-gray-ui-") as temporary:
        runtime = Path(temporary)
        copied = runtime / options.filename.name
        shutil.copy2(options.filename, copied)
        language = runtime / "dlcv/language.txt"
        language.parent.mkdir()
        language.write_text("zh-Hans", encoding="utf-8")
        # 与项目既有 UI 验收入口一致：只隔离配置与外部 AI，不替换任何界面。
        class MainWindow(AppMainWindow):
            def __init__(self, *args, **kwargs):
                self.settings = self.createSettings("labelme", "labelme")
                STORE.register_main_window(self)
                dlcv_tr("设置面板")
                super().__init__(*args, **kwargs)

            def createSettings(self, organization, application):
                return QtCore.QSettings(str(runtime / f"{organization}-{application}.ini"),
                                        QtCore.QSettings.IniFormat)

            def _init_dlcv_ai_widget(self):
                pass

        translator = QtCore.QTranslator()
        STORE.q_translator = translator
        STORE.backend_ws = None
        app = QtWidgets.QApplication([sys.argv[0]])
        app.setApplicationName(__appname__)
        app.setWindowIcon(newIcon("icon"))
        app.installTranslator(translator)
        app.setFont(QtGui.QFont("Microsoft YaHei", 10))
        config = get_config(str(runtime / ".labelmerc"), {})
        config["auto_save"] = False
        win = MainWindow(config=config)
        win.ui_theme_manager.set_theme("modern", persist=False, notify=False)
        win.resize(1500, 950)
        win.show()
        win.loadFile(str(copied))
        dock = win.gray_window_dock
        if options.minimum is not None:
            dock.minimum_spin.setValue(options.minimum)
        if options.maximum is not None:
            dock.maximum_spin.setValue(options.maximum)
        dock._timer.stop()
        dock._emit_image()
        # 无图标注面板不占据灰度调节区域，保留真实 Dock 和画布。
        for other in (win.flag_dock, win.label_dock, win.shape_dock,
                      win.label_count_dock, win.setting_dock):
            other.hide()
        dock.show()
        dock.raise_()
        available = win.screen().availableGeometry()
        frame_extra = win.frameGeometry().size() - win.size()
        win.resize(win.size().boundedTo(available.size() - frame_extra))
        frame = win.frameGeometry()
        frame.moveCenter(available.center())
        win.move(frame.topLeft())
        win.adjustScale(initial=True)
        win.paintCanvas()
        QtCore.QTimer.singleShot(60000, app.quit)
        try:
            app.exec_()
        finally:
            win.setClean()
            win.close()
        assert hashlib.sha256(options.filename.read_bytes()).digest() == original_hash


if __name__ == "__main__":
    main()
