"""隔离的截图与界面验收入口。"""
import argparse
import os
import sys
from pathlib import Path

from qtpy import QtCore, QtWidgets

from labelme import __appname__
from labelme.config import get_config
from labelme.dlcv.app import MainWindow
from labelme.utils import newIcon


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--screenshot-output", type=Path, required=True,
        help="在离屏模式下将真实界面绘制到指定目录（需要提供图片路径）",
    )
    parser.add_argument(
        "--screenshot-clear-group", action="store_true",
        help="在临时副本中验证两图整组清空（仅用于 --screenshot-output）",
    )
    parser.add_argument(
        "--screenshot-readonly-save", action="store_true",
        help="在临时只读图片上验证失败与编辑保留（需要 --screenshot-output）",
    )
    parser.add_argument(
        "--screenshot-native", action="store_true",
        help="保留真实主窗口供隔离桌面采集（需要 --screenshot-output）",
    )
    parser.add_argument(
        "--screenshot-refresh", action="store_true",
        help="在临时目录验证刷新按钮读取新增文件夹（需要 --screenshot-output）",
    )
    parser.add_argument(
        "--screenshot-refresh-folders", action="store_true",
        help="验证刷新后折叠目录与实际文件内容（需要 --screenshot-output）",
    )
    parser.add_argument("filename", help="用于验收的图片路径")
    args = parser.parse_args()
    if args.screenshot_refresh and (args.screenshot_readonly_save or args.screenshot_clear_group):
        parser.error("刷新验证不能与保存或整组清空同时使用")
    if args.screenshot_readonly_save and args.screenshot_clear_group:
        parser.error("只读保存验证不能与整组清空同时使用")
    if args.screenshot_refresh_folders and any((
        args.screenshot_refresh, args.screenshot_readonly_save, args.screenshot_clear_group,
    )):
        parser.error("目录折叠验证不能与其他场景同时使用")
    sys.excepthook = sys.__excepthook__
    render_screenshots(
        args.filename, args.screenshot_output, args.screenshot_clear_group,
        readonly_save=args.screenshot_readonly_save, native=args.screenshot_native,
        refresh=args.screenshot_refresh, refresh_folders=args.screenshot_refresh_folders,
    )


def check_refresh_folders(win, app, root_dir, sample, output_dir, capture):
    import json
    from qtpy import QtGui

    expected_contents = {
        "balloon": ["OK", "train", "val"],
        "balloon/OK": ["样例.jpg"],
        "balloon/train": ["样例.jpg"],
        "balloon/val": ["样例.jpg"],
        "气球测试": ["子目录"],
        "气球测试/子目录": ["样例.jpg"],
        "元器件外观检测": ["1.jpg", "2.jpg"],
    }
    image = QtGui.QImage(str(sample))
    if image.isNull():
        raise RuntimeError("目录验收图片无法读取")
    for directory, names in expected_contents.items():
        for name in names:
            if name.endswith(".jpg"):
                path = root_dir / directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if not image.save(str(path), "JPEG"):
                    raise RuntimeError(f"目录验收图片无法保存: {directory}/{name}")

    tree = win.fileListWidget.tree_widget
    top_names = {"balloon", "气球测试", "元器件外观检测"}

    def find_folder(relative_path):
        path = (root_dir / relative_path).as_posix()
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == path:
                return item
            iterator += 1
        return None

    def snapshot():
        current = tree.currentItem()
        path = current.data(0, QtCore.Qt.UserRole) if current is not None else None
        return {
            "expanded": {
                Path(item.data(0, QtCore.Qt.UserRole)).name: item.isExpanded()
                for item in (tree.topLevelItem(index)
                             for index in range(tree.topLevelItemCount()))
            },
            "has_current_item": current is not None,
            "current_item_path": Path(path).relative_to(root_dir).as_posix() if path else None,
            "selected_count": len(tree.selectedItems()),
        }

    def remains_collapsed(state):
        return (
            set(state["expanded"]) == top_names
            and not any(state["expanded"].values())
            and not state["has_current_item"]
            and state["selected_count"] == 0
        )

    def inspect_directory(directory, expected, expand):
        item = find_folder(directory)
        actual = []
        if item is not None:
            if expand:
                item.setExpanded(False)
                item.setExpanded(True)
                app.processEvents()
            actual = [
                Path(child.data(0, QtCore.Qt.UserRole)).name
                if child.data(0, QtCore.Qt.UserRole) else ""
                for child in (item.child(index) for index in range(item.childCount()))
            ]
        return {
            "directory": directory, "expected": expected, "actual": actual,
            "found": item is not None, "success": item is not None and actual == expected,
        }

    win.setClean()
    win.importDirImages(str(root_dir), load=False)
    tree.collapseAll()
    tree.clearSelection()
    tree.setCurrentItem(None)
    app.processEvents()
    before = snapshot()
    capture(win, "文件夹刷新前.png")
    win.action_refresh.trigger()
    app.processEvents()
    after = snapshot()
    capture(win, "文件夹首次刷新.png")

    checks = [inspect_directory(directory, expected, expand=True)
              for directory, expected in expected_contents.items()]

    tree.collapseAll()
    tree.clearSelection()
    tree.setCurrentItem(None)
    win.action_refresh.trigger()
    app.processEvents()
    repeated = snapshot()
    repeated_contents = [inspect_directory(directory, expected, expand=False)
                         for directory, expected in expected_contents.items()]
    result = {
        "expected_top_directories": sorted(top_names),
        "before": before, "after": after, "repeated": repeated,
        "contents": checks, "repeated_contents": repeated_contents,
        "first_refresh_success": remains_collapsed(before) and remains_collapsed(after),
        "repeated_refresh_success": remains_collapsed(repeated),
    }
    result["success"] = all((
        result["first_refresh_success"], result["repeated_refresh_success"],
        all(check["success"] for check in checks),
        all(check["success"] for check in repeated_contents),
    ))
    if result["success"]:
        find_folder("balloon").setExpanded(True)
    else:
        win.importDirImages(str(root_dir), load=False)
        tree.clearSelection()
        tree.setCurrentItem(None)
        win.action_refresh.trigger()
    app.processEvents()
    result["displayed"] = snapshot()
    (output_dir / "文件夹刷新验证.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    win.setWindowTitle(win.windowTitle() + " · 文件夹刷新验收")


def render_screenshots(filename, output_dir, clear_group=False, *, readonly_save=False, native=False, refresh=False, refresh_folders=False):
    """通过正式主窗检查隔离副本，不启动外部服务。"""
    import json
    import shutil
    import stat
    import tempfile

    from qtpy import QtGui

    from labelme.dlcv import dlcv_tr
    from labelme.dlcv.store import STORE

    source = Path(filename).resolve(strict=True)
    if source.suffix.lower() == ".json":
        raise ValueError("截图模式不接受 JSON 入参，请提供图片路径")
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_dir():
        raise NotADirectoryError(output_dir)
    names = ("主窗口.png", "设置面板.png", "标注页.png")
    extra_names = ("清空前主窗口.png", "清空验证.json") if clear_group else ()
    if readonly_save:
        extra_names += ("只读保存验证.json",)
    if refresh:
        extra_names += ("刷新验证.json",)
    if refresh_folders:
        extra_names += ("文件夹刷新前.png", "文件夹首次刷新.png", "文件夹刷新验证.json")
    if any((output_dir / name).exists() for name in names + extra_names):
        raise FileExistsError("截图文件已存在，请选择空目录")

    image_paths = [source]
    if clear_group:
        from dlcv_core.image_json import has_image_json
        from labelme.dlcv.label_file import LabelFile, collect_image_paths

        label_file = LabelFile(str(source))
        image_paths = [
            path.resolve(strict=True)
            for path in collect_image_paths(source, label_file.otherData)
        ]
        if len(image_paths) != 2 or len(set(image_paths)) != 2:
            raise ValueError("清空校验需要同一组中的两张图片")
        for path in image_paths:
            if path.parent != source.parent:
                raise ValueError("清空校验只接受同目录组图片")
            json_path = path.with_suffix(".json").resolve(strict=True)
            if json_path.parent != source.parent:
                raise ValueError("清空校验只接受同目录 JSON")
            member = LabelFile(str(path))
            if Path(member.imagePath).is_absolute() or any(
                item.parent != Path(".")
                for item in collect_image_paths(Path(path.name), member.otherData)
            ):
                raise ValueError("清空校验的组名单及图片路径必须使用同目录文件名")
            members = {
                item.resolve(strict=True)
                for item in collect_image_paths(path, member.otherData)
            }
            if not members.issubset(image_paths) or (
                path.parent / member.imagePath
            ).resolve(strict=True) != path:
                raise ValueError("图片及其标注必须属于同一目录中的两图组")

    # Qt 按类名查找主窗翻译，离屏主窗沿用 MainWindow 名称。
    BaseMainWindow = globals()["MainWindow"]

    class MainWindow(BaseMainWindow):
        def __init__(self, *args, **kwargs):
            # 基类创建菜单前，使用此主窗的隔离设置完成翻译懒加载。
            self.settings = self.createSettings("labelme", "labelme")
            STORE.register_main_window(self)
            dlcv_tr("设置面板")
            super().__init__(*args, **kwargs)

        def createSettings(self, organization, application):
            settings = QtCore.QSettings(
                str(settings_dir / f"{organization}-{application}.ini"),
                QtCore.QSettings.IniFormat,
            )
            screenshot_settings.append(settings)
            return settings

        def _init_dlcv_ai_widget(self):
            pass

    with tempfile.TemporaryDirectory(prefix="labelme-ui-") as temp:
        temp_path = Path(temp)
        settings_dir = temp_path / "settings"
        settings_dir.mkdir()
        screenshot_settings = []
        for key in (
            "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"
        ):
            os.environ[key] = str(temp_path)
        image_dir = temp_path / "images" if readonly_save or refresh or refresh_folders else temp_path
        image_dir.mkdir(exist_ok=True)
        copied = image_dir / source.name
        for path in image_paths:
            shutil.copy2(path, image_dir / path.name)
            json_path = path.with_suffix(".json")
            if json_path.is_file():
                shutil.copy2(json_path, image_dir / json_path.name)
        config = get_config(str(temp_path / ".labelmerc"), {})
        config["auto_save"] = False
        language_file = temp_path / "dlcv" / "language.txt"
        language_file.parent.mkdir(parents=True, exist_ok=True)
        language_file.write_text("zh-Hans", encoding="utf-8")
        translator = QtCore.QTranslator()
        STORE.q_translator = translator
        STORE.backend_ws = None
        app = QtWidgets.QApplication([sys.argv[0]])
        app.setApplicationName(__appname__)
        app.setWindowIcon(newIcon("icon"))
        app.installTranslator(translator)
        if sys.platform == "win32":
            font_path = Path(os.environ.get("WINDIR", "")) / "Fonts" / "msyh.ttc"
            if font_path.exists():
                font_id = QtGui.QFontDatabase.addApplicationFont(str(font_path))
                families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    app.setFont(QtGui.QFont(families[0], 10))

        if readonly_save:
            copied.chmod(stat.S_IREAD)
        win = None
        try:
            win = MainWindow(config=config, filename=str(copied))
            if refresh or refresh_folders:
                win.ui_theme_manager.set_theme("modern", persist=False, notify=False)
            win.resize(1920, 1080)
            win.show()  # offscreen 平台不创建桌面窗口
            if app.platformName() != "offscreen":
                available = win.screen().availableGeometry()
                frame_size = win.frameGeometry().size() - win.size()
                win.resize(win.size().boundedTo(available.size() - frame_size))
                frame = win.frameGeometry()
                frame.moveCenter(available.center())
                win.move(frame.topLeft())
            for _ in range(5):
                app.processEvents()
            if (
                dlcv_tr.get_lang() != "zh_CN"
                or translator.isEmpty()
                or win.file_dock.windowTitle() != "文件列表"
            ):
                raise RuntimeError("未通过设置完成中文翻译懒加载")
            if win.filename != str(copied) or win.image.isNull():
                raise RuntimeError("图片未能通过主窗口加载")
            if (clear_group or readonly_save) and not win.canvas.shapes:
                raise RuntimeError("保存验证需要原有非空标注")

            def capture(widget, name):
                image = QtGui.QImage(widget.size(), QtGui.QImage.Format_ARGB32)
                image.fill(QtGui.QColor("white"))
                widget.render(image)
                if image.isNull() or not image.save(str(output_dir / name)):
                    raise RuntimeError(f"界面绘制失败: {name}")

            if readonly_save:
                from dlcv_core.image_json import read_image_json
                before = copied.read_bytes()
                win.setClean()
                win.importDirImages(str(image_dir), load=False)
                win.loadFile(str(copied))
                win._update_item(
                    item=win.labelList.findItemByShape(win.canvas.shapes[0]),
                    text="未保存验证", flags=None, group_id=None, description=None,
                )
                errors = []
                # 非交互检查保留失败信息，不等待弹窗输入。
                win.errorMessage = lambda title, message: errors.append(str(message))
                save_result = win.saveFile()
                result = {
                    "window_title": win.windowTitle(),
                    "save_returned": save_result,
                    "edited_label": win.canvas.shapes[0].label,
                    "image_unchanged": copied.read_bytes() == before,
                    "image_readonly": not bool(copied.stat().st_mode & stat.S_IWRITE),
                    "embedded_annotation": read_image_json(copied),
                    "dirty": win.dirty,
                    "errors": errors,
                }
                result["success"] = all((
                    not save_result, win.dirty, bool(errors),
                    result["edited_label"] == "未保存验证",
                    result["image_unchanged"], result["image_readonly"],
                    result["embedded_annotation"] is None,
                ))
                (output_dir / "只读保存验证.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                if not result["success"]:
                    raise RuntimeError("只读保存失败处理检查未通过")
                app.processEvents()

            if clear_group:
                win._config["auto_save"] = False
                win.actions.saveAuto.setChecked(False)
                win.fileListWidget.set_root_dir(str(temp_path))
                results = []
                for path in image_paths:
                    image_path = temp_path / path.name
                    if (
                        not win.loadFile(str(image_path))
                        or win.filename != str(image_path)
                    ):
                        raise RuntimeError(f"组图片未能加载: {path.name}")
                    count = len(win.canvas.shapes)
                    items = win.fileListWidget.findItems(str(image_path))
                    if not count or not win.hasLabelFile() or not items or any(
                        item.checkState(0) != QtCore.Qt.Checked for item in items
                    ):
                        raise RuntimeError(f"清空前标注或文件树状态错误: {path.name}")
                    results.append({"name": path.name, "before_label_count": count})
                if not win.loadFile(str(copied)):
                    raise RuntimeError("清空前首图未能加载")
                app.processEvents()
                capture(win, "清空前主窗口.png")
                win.canvas.selectShapes(win.canvas.shapes)
                win.deleteSelectedShape()
                if not win.saveFile():
                    raise RuntimeError("整组清空保存失败")
                for result in results:
                    image_path = temp_path / result["name"]
                    result["embedded_json_exists"] = has_image_json(image_path)
                    result["external_json_exists"] = image_path.with_suffix(
                        ".json"
                    ).exists()
                    if (
                        not win.loadFile(str(image_path))
                        or win.filename != str(image_path)
                    ):
                        raise RuntimeError(f"清空后组图片未能重开: {result['name']}")
                    app.processEvents()
                    result["reopened_label_count"] = len(win.canvas.shapes)
                    result["has_label_file"] = win.hasLabelFile()
                    items = win.fileListWidget.findItems(str(image_path))
                    result["file_tree_checked"] = any(
                        item.checkState(0) != QtCore.Qt.Unchecked for item in items
                    )
                    result["success"] = bool(items) and not any((
                        result["embedded_json_exists"], result["external_json_exists"],
                        result["reopened_label_count"], result["has_label_file"],
                        result["file_tree_checked"],
                    ))
                success = all(result["success"] for result in results)
                (output_dir / "清空验证.json").write_text(
                    json.dumps({"success": success, "images": results},
                               ensure_ascii=False, indent=2), encoding="utf-8",
                )
                if not success:
                    raise RuntimeError("整组清空校验失败，详见清空验证.json")
                if not win.loadFile(str(copied)):
                    raise RuntimeError("清空后首图未能加载")
                app.processEvents()

            if refresh:
                win.setClean()
                win.importDirImages(str(image_dir), load=False)
                tree = win.fileListWidget.tree_widget
                tree.setCurrentRow(tree.image_list.index(copied.as_posix()))
                win.loadFile(str(copied))
                added_dir = image_dir / "新增文件夹"
                added_dir.mkdir()
                shutil.copy2(copied, added_dir / copied.name)
                before_filename = win.filename
                before_shapes = list(win.canvas.shapes)
                win.action_refresh.trigger()
                app.processEvents()
                directory_names = [
                    tree.topLevelItem(index).super_text(0)
                    for index in range(tree.topLevelItemCount())
                ]
                result = {
                    "directory_names": directory_names,
                    "new_directory_visible": added_dir.name in directory_names,
                    "current_image_preserved": win.filename == before_filename,
                    "annotations_preserved": win.canvas.shapes == before_shapes,
                    "shortcut": win.action_refresh.shortcut().toString(),
                }
                result["success"] = all((
                    result["new_directory_visible"], result["current_image_preserved"],
                    result["annotations_preserved"], result["shortcut"] == "F5",
                ))
                (output_dir / "刷新验证.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                win.setWindowTitle(win.windowTitle() + " · 刷新验证")

            if refresh_folders:
                check_refresh_folders(
                    win, app, image_dir / "文件夹验收", copied, output_dir, capture,
                )

            if native:
                QtCore.QTimer.singleShot(60000, app.quit)
                app.exec_()
                return
            capture(win, names[0])
            capture(win.canvas, names[2])
            for dock in (win.flag_dock, win.label_dock, win.shape_dock,
                         win.label_count_dock):
                dock.hide()
            app.processEvents()
            capture(win.setting_dock, names[1])
        finally:
            try:
                if readonly_save:
                    copied.chmod(stat.S_IREAD | stat.S_IWRITE)
                if win is not None:
                    win.setClean()
                    win.close()
                    app.processEvents()
            finally:
                STORE.q_translator = None
                settings_errors = []
                for settings in screenshot_settings:
                    settings.sync()
                    if settings.status() != QtCore.QSettings.NoError:
                        settings_errors.append(settings.fileName())
                if settings_errors:
                    raise RuntimeError(f"截图设置同步失败: {settings_errors}")


if __name__ == "__main__":
    main()
