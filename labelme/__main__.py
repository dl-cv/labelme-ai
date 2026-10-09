# ruff: noqa: I001
import os
import sys
from pathlib import Path

# 离屏模式必须在首次加载 Qt 之前指定平台。
if "--screenshot-output" in sys.argv and "--screenshot-native" not in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

# 判断是否是 python 启动
if sys.argv[-1].endswith('.py'):
    labelme_path = str(Path(__file__).parent.parent)
    print(f"labelme_path: {labelme_path}")
    sys.path.insert(0, labelme_path)

from labelme.logger import logger  # noqa: F401 先导入logger，防止未正常启动exe就报错

import argparse
import asyncio
import codecs
import logging

import yaml
from qtpy import QtCore
from qtpy import QtWidgets

from labelme import __appname__
from labelme import __version__
from labelme.config import get_config
from labelme.dlcv.app import MainWindow
from labelme.utils import newIcon


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", "-V", action="store_true", help="show version")
    parser.add_argument("--reset-config", action="store_true", help="reset qt config")
    parser.add_argument(
        "--screenshot-output", type=Path,
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
        "--logger-level",
        default="debug",
        choices=["debug", "info", "warning", "fatal", "error"],
        help="logger level",
    )
    parser.add_argument("filename", nargs="?", help="image or label filename")
    parser.add_argument(
        "--output",
        "-O",
        "-o",
        help="output file or directory (if it ends with .json it is "
             "recognized as file, else as directory)",
    )
    default_config_file = os.path.join(os.path.expanduser("~"), ".labelmerc")
    parser.add_argument(
        "--config",
        dest="config",
        help="config file or yaml-format string (default: {})".format(
            default_config_file
        ),
        default=default_config_file,
    )
    # config for the gui
    parser.add_argument(
        "--nodata",
        dest="store_data",
        action="store_false",
        help="stop storing image data to JSON file",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--autosave",
        dest="auto_save",
        action="store_true",
        help="auto save",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--nosortlabels",
        dest="sort_labels",
        action="store_false",
        help="stop sorting labels",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--flags",
        help="comma separated list of flags OR file containing flags",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--labelflags",
        dest="label_flags",
        help=r"yaml string of label specific flags OR file containing json "
             r"string of label specific flags (ex. {person-\d+: [male, tall], "
             r"dog-\d+: [black, brown, white], .*: [occluded]})",  # NOQA
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--labels",
        help="comma separated list of labels OR file containing labels",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--validatelabel",
        dest="validate_label",
        choices=["exact"],
        help="label validation types",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep-prev",
        action="store_true",
        help="keep annotation of previous frame",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        help="epsilon to find nearest vertex on canvas",
        default=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.screenshot_clear_group and args.screenshot_output is None:
        parser.error("--screenshot-clear-group 必须与 --screenshot-output 一起使用")
    if (args.screenshot_readonly_save or args.screenshot_native) and args.screenshot_output is None:
        parser.error("截图验证参数需要 --screenshot-output")
    if args.screenshot_readonly_save and args.screenshot_clear_group:
        parser.error("只读保存验证不能与整组清空同时使用")
    if args.screenshot_output is not None:
        if not args.filename or args.output or args.reset_config:
            parser.error(
                "截图模式需要图片路径，且不能与 --output 或 --reset-config 一起使用"
            )
        if args.screenshot_clear_group or args.screenshot_readonly_save:
            # 清空校验失败直接退出，不弹出等待交互的异常对话框。
            sys.excepthook = sys.__excepthook__
        render_screenshots(
            args.filename, args.screenshot_output, args.screenshot_clear_group,
            readonly_save=args.screenshot_readonly_save, native=args.screenshot_native,
        )
        return

    if args.version:
        print("{0} {1}".format(__appname__, __version__))
        sys.exit(0)

    logger.setLevel(getattr(logging, args.logger_level.upper()))

    if hasattr(args, "flags"):
        if os.path.isfile(args.flags):
            with codecs.open(args.flags, "r", encoding="utf-8") as f:
                args.flags = [line.strip() for line in f if line.strip()]
        else:
            args.flags = [line for line in args.flags.split(",") if line]

    if hasattr(args, "labels"):
        if os.path.isfile(args.labels):
            with codecs.open(args.labels, "r", encoding="utf-8") as f:
                args.labels = [line.strip() for line in f if line.strip()]
        else:
            args.labels = [line for line in args.labels.split(",") if line]

    if hasattr(args, "label_flags"):
        if os.path.isfile(args.label_flags):
            with codecs.open(args.label_flags, "r", encoding="utf-8") as f:
                args.label_flags = yaml.safe_load(f)
        else:
            args.label_flags = yaml.safe_load(args.label_flags)

    config_from_args = args.__dict__
    config_from_args.pop("version")
    config_from_args.pop("screenshot_clear_group")
    reset_config = config_from_args.pop("reset_config")

    # extra 支持 dva 文件
    filename = config_from_args.pop("filename")
    if filename:
        if filename.endswith(".dva"):
            filename = None
        elif os.path.isdir(filename):
            filename = None
        # https://bbs2.dlcv.com.cn/t/topic/1532
        elif len(filename) == 3 and filename[1] == ':' and filename[0].isalpha():
            filename = None
    # extra End
    output = config_from_args.pop("output")
    config_file_or_yaml = config_from_args.pop("config")
    config = get_config(config_file_or_yaml, config_from_args)

    if not config["labels"] and config["validate_label"]:
        logger.error(
            "--labels must be specified with --validatelabel or "
            "validate_label: true in the config file "
            "(ex. ~/.labelmerc)."
        )
        sys.exit(1)

    output_file = None
    output_dir = None
    if output is not None:
        if output.endswith(".json"):
            output_file = output
        else:
            output_dir = output

    # 更新翻译文件
    # with open('translate/zh_CN.qm', 'rb') as f:
    #     x = f.read()
    #     with open('translate/zh_CN.py', 'w') as tf:
    #         tf.write(f"translate_data = {repr(x)}")

    start_backend()

    # 初始化 WebSocket 连接（同步调用）
    try:
        from labelme.dlcv.app import init_backend_ws
        init_backend_ws()
    except Exception as e:
        logger.error(f"WebSocket initialization failed: {e}")

    from labelme.dlcv.store import STORE
    translator = QtCore.QTranslator()
    STORE.q_translator = translator

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("icon"))
    app.installTranslator(translator)
    win = MainWindow(
        config=config,
        filename=filename,
        output_file=output_file,
        output_dir=output_dir,
    )

    if reset_config:
        logger.info("Resetting Qt config: %s" % win.settings.fileName())
        win.settings.clear()
        sys.exit(0)

    win.show()
    win.raise_()


    from qasync import QEventLoop

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        loop.run_forever()
    
    sys.exit()


def render_screenshots(filename, output_dir, clear_group=False, *, readonly_save=False, native=False):
    """通过正式主窗检查隔离副本，不启动外部服务。"""
    import json
    import shutil
    import stat
    import tempfile

    from qtpy import QtGui

    from labelme.dlcv import dlcv_tr
    from labelme.dlcv.store import STORE

    source = Path(filename).resolve(strict=True)
    annotation = source.with_suffix(".json")
    if not annotation.is_file():
        raise FileNotFoundError(annotation)
    output_dir = Path(output_dir).resolve()
    if not output_dir.is_dir():
        raise NotADirectoryError(output_dir)
    names = ("主窗口.png", "设置面板.png", "标注页.png")
    extra_names = ("清空前主窗口.png", "清空验证.json") if clear_group else ()
    if readonly_save:
        extra_names += ("只读保存验证.json",)
    if any((output_dir / name).exists() for name in names + extra_names):
        raise FileExistsError("截图文件已存在，请选择空目录")

    image_paths = [source]
    if clear_group:
        from dlcv_core.image_json import has_image_json
        from labelme.dlcv.label_file import LabelFile, _collect_image_paths

        label_file = LabelFile(str(source))
        image_paths = [
            path.resolve(strict=True)
            for path in _collect_image_paths(source, label_file.otherData)
        ]
        if len(image_paths) != 2 or len(set(image_paths)) != 2:
            raise ValueError("清空校验需要同一组中的两张图片")
        for path in image_paths:
            if path.parent != source.parent:
                raise ValueError("清空校验只接受同目录组图片")
            sidecar = path.with_suffix(".json").resolve(strict=True)
            if sidecar.parent != source.parent:
                raise ValueError("清空校验只接受同目录 JSON")
            member = LabelFile(str(path))
            if Path(member.imagePath).is_absolute() or any(
                item.parent != Path(".")
                for item in _collect_image_paths(Path(path.name), member.otherData)
            ):
                raise ValueError("清空校验的组名单及图片路径必须使用同目录文件名")
            members = {
                item.resolve(strict=True)
                for item in _collect_image_paths(path, member.otherData)
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
            self.settings = QtCore.QSettings("labelme", "labelme")
            STORE.register_main_window(self)
            dlcv_tr("设置面板")
            super().__init__(*args, **kwargs)

        def _init_dlcv_ai_widget(self):
            pass

    with tempfile.TemporaryDirectory(prefix="labelme-ui-") as temp:
        temp_path = Path(temp)
        for key in (
            "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"
        ):
            os.environ[key] = str(temp_path)
        image_dir = temp_path / "images" if readonly_save else temp_path
        image_dir.mkdir(exist_ok=True)
        copied = image_dir / source.name
        for path in image_paths:
            shutil.copy2(path, image_dir / path.name)
            sidecar = path.with_suffix(".json")
            shutil.copy2(sidecar, image_dir / sidecar.name)
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
        for scope in (QtCore.QSettings.UserScope, QtCore.QSettings.SystemScope):
            QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, scope, str(temp_path))
        config = get_config(str(temp_path / ".labelmerc"), {})
        if clear_group or readonly_save:
            # 验收副本从首次加载起禁用自动保存。
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
        win = MainWindow(config=config, filename=str(copied))
        try:
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
            if win.filename != str(copied) or not win.canvas.shapes:
                raise RuntimeError("图片或原有标注未能通过主窗口加载")

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
            if readonly_save:
                copied.chmod(stat.S_IREAD | stat.S_IWRITE)
            if clear_group or readonly_save:
                win.setClean()
            win.close()
            app.processEvents()
            STORE.q_translator = None


def start_backend():
    """启动后端服务"""
    try:
        from labelme.private.dlcv_ai_widget import start_server
        start_server()
    except Exception as e:
        logger.debug(f"后端启动失败: {e}")


# this main block is required to generate executable by pyinstaller
if __name__ == "__main__":
    main()
