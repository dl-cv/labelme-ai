"""使用真实主窗口进行隔离、非交互界面检查。"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--theme", choices=["default", "modern", "classic"], default="default")
    parser.add_argument("--font-size", type=int, default=10)
    parser.add_argument("--menu", action="store_true")
    parser.add_argument("--hold", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    # Windows 验证必须通过独立桌面入口运行，禁止读写使用中的配置。
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "ScreenshotIsolation") as key:
            winreg.QueryValueEx(key, "ScreenshotIsolation")
    source = args.source.resolve()
    report_path = args.report.resolve()
    sys.path.insert(0, str(source))
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="labelme-ui-qa-", dir=original_cwd) as directory:
        root = Path(directory)
        for name in ("profile", "logs", "settings", "data"):
            (root / name).mkdir()
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(root / "profile")
        os.environ["LABELME_LOG_DIR"] = str(root / "logs")
        os.environ["QT_API"] = "pyqt5"
        from qtpy import QtCore, QtWidgets

        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
        for scope in (QtCore.QSettings.UserScope, QtCore.QSettings.SystemScope):
            QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, scope, str(root / "settings"))
        settings = QtCore.QSettings("labelme", "labelme")
        settings.setValue("ui/language", "zh_CN")
        settings.setValue("ui/font_point_size", args.font_size)
        settings.setValue("window/size", QtCore.QSize(1920, 1100))
        if args.theme != "default":
            settings.setValue("ui/theme", args.theme)
        settings.sync()
        saved_theme_before = settings.value("ui/theme")
        from labelme import __appname__
        from labelme.config import get_config
        from labelme.dlcv.app import MainWindow
        from labelme.dlcv.store import STORE
        from labelme.utils import newIcon

        app = QtWidgets.QApplication([])
        app.setApplicationName(__appname__)
        app.setWindowIcon(newIcon("icon"))
        translator = QtCore.QTranslator()
        STORE.q_translator = translator
        app.installTranslator(translator)
        # 使用仓库公开样例副本，不修改样例源文件。
        sample = source / "examples/bbox_detection/data_annotated"
        for suffix in ("jpg", "json"):
            shutil.copy2(sample / f"2011_000003.{suffix}", root / "data" / f"2011_000003.{suffix}")
        os.chdir(root / "data")
        window = MainWindow(config=get_config(), filename="2011_000003.jpg")
        window.show()
        window.resizeDocks([window.setting_dock], [620], QtCore.Qt.Horizontal)
        exit_code = [0]

        def check():
            try:
                labels = []
                widget = window.uniqLabelList
                for row in range(widget.count()):
                    item = widget.item(row)
                    label = widget.itemWidget(item)
                    labels.append({
                        "text": item.data(QtCore.Qt.UserRole),
                        "row_height": widget.visualItemRect(item).height(),
                        "contents_height": label.contentsRect().height(),
                        "font_height": label.fontMetrics().height(),
                    })
                shape_rows = []
                shape_list = window.labelList
                for row in range(shape_list.model().rowCount()):
                    index = shape_list.model().index(row, 0)
                    option = shape_list.viewOptions()
                    option.widget = shape_list
                    option.rect = shape_list.visualRect(index)
                    delegate = shape_list.itemDelegate()
                    delegate.initStyleOption(option, index)
                    delegate.sizeHint(option, index)
                    if hasattr(delegate, "textRect"):
                        rect = delegate.textRect(option)
                        shape_rows.append({
                            "row": row,
                            "text_height": rect.height(),
                            "document_height": delegate.doc.size().height(),
                        })
                docks = []
                for dock in (window.label_dock, window.shape_dock, window.setting_dock, window.label_count_dock):
                    bar = dock.titleBarWidget()
                    title = bar.findChild(QtWidgets.QLabel, "dlcvDockTitleLabel") if bar else None
                    docks.append({
                        "title": dock.windowTitle(),
                        "custom_title": bar is not None,
                        "title_height": title.height() if title else None,
                        "font_height": title.fontMetrics().height() if title else None,
                    })
                menu = window.ui_theme_manager._theme_menu
                result = {
                    "saved_theme_before": saved_theme_before,
                    "active_theme": window.ui_theme_manager.current_theme,
                    "font_size": args.font_size,
                    "labels": labels,
                    "shape_rows": shape_rows,
                    "docks": docks,
                    "label_tooltip": widget.toolTip(),
                    "menu": [{"text": a.text(), "checked": a.isChecked()} for a in menu.actions()],
                }
                errors = []
                if args.verify:
                    if result["active_theme"] != ("modern" if args.theme == "default" else args.theme):
                        errors.append("默认主题错误")
                    if "Esc" in window.label_dock.windowTitle() or "Esc" in widget.toolTip():
                        errors.append("仍含错误的 Esc 提示")
                    if menu.actions()[1].text() != "原版UI（原生）":
                        errors.append("原版界面括号文字错误")
                    for label in labels:
                        if label["contents_height"] < label["font_height"]:
                            errors.append("标签文字显示空间不足")
                    for row in shape_rows:
                        if row["text_height"] < row["document_height"]:
                            errors.append("多边形标签文字显示空间不足")
                    if result["active_theme"] == "modern":
                        for dock in docks:
                            if not dock["custom_title"] or dock["title_height"] < dock["font_height"]:
                                errors.append("标题显示空间不足")
                result["errors"] = errors
                report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                if errors:
                    exit_code[0] = 1
                if args.menu:
                    menu.setWindowTitle(menu.title())
                    menu.popup(window.mapToGlobal(QtCore.QPoint(340, 80)))
                if not args.hold:
                    window.close()
                    app.quit()
            except Exception:
                import traceback
                report_path.write_text(traceback.format_exc(), encoding="utf-8")
                exit_code[0] = 1
                app.quit()

        QtCore.QTimer.singleShot(1200, check)
        QtCore.QTimer.singleShot(60000, app.quit)
        app.exec_()
        window.close()
        settings.sync()
        import logging
        logging.shutdown()
        os.chdir(original_cwd)
        return exit_code[0]


if __name__ == "__main__":
    sys.exit(main())
