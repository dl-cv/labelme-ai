# ruff: noqa: I001
import os
import sys
from pathlib import Path

# 离屏模式必须在首次加载 Qt 之前指定平台。
if "--screenshot-output" in sys.argv:
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
    if args.screenshot_output is not None:
        if not args.filename or args.output or args.reset_config:
            parser.error(
                "截图模式需要图片路径，且不能与 --output 或 --reset-config 一起使用"
            )
        render_screenshots(args.filename, args.screenshot_output)
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


def render_screenshots(filename, output_dir):
    """使用正式主窗离屏绘制隔离数据，不启动外部服务。"""
    import shutil
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
    if any((output_dir / name).exists() for name in names):
        raise FileExistsError("截图文件已存在，请选择空目录")

    # 仅在离屏模式下禁用需要外部授权的 AI 工具栏；其余控件均由正式主窗创建。
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
        copied = temp_path / source.name
        shutil.copy2(source, copied)
        shutil.copy2(annotation, temp_path / annotation.name)
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
        for scope in (QtCore.QSettings.UserScope, QtCore.QSettings.SystemScope):
            QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, scope, str(temp_path))
        config = get_config(str(temp_path / ".labelmerc"), {})
        settings = QtCore.QSettings("labelme", "labelme")
        settings.setValue("ui/language", "zh_CN")
        settings.sync()
        if settings.status() != QtCore.QSettings.NoError:
            raise RuntimeError("隔离语言设置写入失败")
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

        win = MainWindow(config=config, filename=str(copied))
        try:
            win.resize(1920, 1080)
            win.show()  # offscreen 平台不创建桌面窗口
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

            capture(win, names[0])
            capture(win.canvas, names[2])
            for dock in (win.flag_dock, win.label_dock, win.shape_dock,
                         win.label_count_dock):
                dock.hide()
            app.processEvents()
            capture(win.setting_dock, names[1])
        finally:
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
