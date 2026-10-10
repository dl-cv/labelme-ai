# ruff: noqa: I001
import os
import sys
from pathlib import Path

# 离屏模式必须在首次加载 Qt 之前指定平台。
screenshot_requested = any(
    arg == "--screenshot-output" or arg.startswith("--screenshot-output=")
    for arg in sys.argv[1:]
)
if screenshot_requested and "--screenshot-native" not in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def launch_native_screenshot():
    """以正式 STARTUPINFO 在不可见桌面运行截图，保存本次子进程诊断。"""
    import argparse
    import ctypes as c
    from ctypes import wintypes as w
    import msvcrt
    import secrets
    import subprocess
    import tempfile

    if sys.platform != "win32":
        raise RuntimeError("原生完整窗口截图仅支持 Windows")
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--screenshot-output", type=Path, required=True)
    args, _ = parser.parse_known_args()
    output_dir = args.screenshot_output.resolve(strict=True)
    if not output_dir.is_dir():
        raise NotADirectoryError(output_dir)
    diagnostic = output_dir / "原生运行日志.txt"
    if diagnostic.exists():
        raise FileExistsError(diagnostic)

    class StartupInfo(c.Structure):
        _fields_ = [
            ("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR),
            ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD),
            ("dwXSize", w.DWORD), ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD),
            ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD),
            ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD),
            ("lpReserved2", c.c_void_p), ("hStdInput", w.HANDLE),
            ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE),
        ]

    class ProcessInfo(c.Structure):
        _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE),
                    ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]

    user32 = c.WinDLL("user32", use_last_error=True)
    kernel32 = c.WinDLL("kernel32", use_last_error=True)
    for dll, name, result, arguments in (
        (user32, "CreateDesktopW", w.HANDLE,
         [w.LPCWSTR, c.c_void_p, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p]),
        (user32, "CloseDesktop", w.BOOL, [w.HANDLE]),
        (kernel32, "CreateProcessW", w.BOOL,
         [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD,
          c.c_void_p, w.LPCWSTR, c.POINTER(StartupInfo), c.POINTER(ProcessInfo)]),
        (kernel32, "WaitForSingleObject", w.DWORD, [w.HANDLE, w.DWORD]),
        (kernel32, "GetExitCodeProcess", w.BOOL, [w.HANDLE, c.POINTER(w.DWORD)]),
        (kernel32, "TerminateProcess", w.BOOL, [w.HANDLE, w.UINT]),
        (kernel32, "CloseHandle", w.BOOL, [w.HANDLE]),
    ):
        function = getattr(dll, name)
        function.restype = result
        function.argtypes = arguments

    def check(result):
        if not result:
            raise c.WinError(c.get_last_error())
        return result

    desktop_name = "LabelmeScreenshot_" + secrets.token_hex(16)
    desktop = None
    exit_status = None
    failures = []
    output = log = ""
    try:
        # 不申请切换桌面权限，窗口仅在本次不可见桌面创建。
        desktop = check(user32.CreateDesktopW(desktop_name, None, None, 0, 0xC3, None))
        with tempfile.TemporaryDirectory(prefix="labelme-native-", ignore_cleanup_errors=True) as temp:
            env = os.environ.copy()
            for key in (
                "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "LABELME_LOG_DIR",
            ):
                env[key] = temp
            env["LABELME_SCREENSHOT_DESKTOP"] = desktop_name
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONUTF8"] = "1"
            env["QT_QPA_PLATFORM"] = "windows"
            if getattr(sys, "frozen", False) or "__compiled__" in globals():
                command = [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
            else:
                env["PYTHONPATH"] = os.pathsep.join(filter(None, (
                    str(Path(__file__).resolve().parent.parent), env.get("PYTHONPATH"),
                )))
                command = [sys.executable, "-B", str(Path(__file__).resolve()), *sys.argv[1:]]
            command_line = c.create_unicode_buffer(subprocess.list2cmdline(command))
            environment = c.create_unicode_buffer("\0".join(
                f"{key}={value}" for key, value in
                sorted(env.items(), key=lambda pair: pair[0].upper())
            ) + "\0\0")
            process = ProcessInfo()
            stream_path = Path(temp) / "子进程输出.txt"
            with stream_path.open("w+b", buffering=0) as stream, open(os.devnull, "rb") as stdin:
                startup = StartupInfo()
                startup.cb = c.sizeof(startup)
                # Python subprocess.STARTUPINFO 不传递 lpDesktop，必须使用原生结构。
                startup.lpDesktop = desktop_name
                startup.dwFlags = subprocess.STARTF_USESTDHANDLES
                startup.hStdInput = msvcrt.get_osfhandle(stdin.fileno())
                startup.hStdOutput = startup.hStdError = msvcrt.get_osfhandle(stream.fileno())
                os.set_handle_inheritable(startup.hStdInput, True)
                os.set_handle_inheritable(startup.hStdOutput, True)
                created = False
                try:
                    check(kernel32.CreateProcessW(
                        command[0], command_line, None, None, True,
                        subprocess.CREATE_NO_WINDOW | 0x400,
                        environment, None, c.byref(startup), c.byref(process),
                    ))
                    created = True
                    status = kernel32.WaitForSingleObject(process.hProcess, 45000)
                    if status == 0x102:
                        failures.append("WaitForSingleObject：45秒主等待超时")
                    elif status != 0:
                        failures.append(f"WaitForSingleObject 返回 {status:#x}：{c.WinError(c.get_last_error())}")
                finally:
                    if created:
                        try:
                            status = kernel32.WaitForSingleObject(process.hProcess, 0)
                            if status != 0:
                                if not kernel32.TerminateProcess(process.hProcess, 1):
                                    failures.append(f"TerminateProcess 失败：{c.WinError(c.get_last_error())}")
                                status = kernel32.WaitForSingleObject(process.hProcess, 5000)
                                if status != 0:
                                    failures.append(f"终止后5秒等待返回 {status:#x}，PID={process.dwProcessId}")
                            if status == 0:
                                code = w.DWORD(0xFFFFFFFF)
                                if kernel32.GetExitCodeProcess(process.hProcess, c.byref(code)):
                                    exit_status = code.value
                                else:
                                    failures.append(f"GetExitCodeProcess 失败：{c.WinError(c.get_last_error())}")
                        finally:
                            for name, handle in (("线程", process.hThread), ("进程", process.hProcess)):
                                if handle and not kernel32.CloseHandle(handle):
                                    failures.append(f"CloseHandle({name}) 失败：{c.WinError(c.get_last_error())}")
                    stream.seek(0)
                    output = stream.read().decode("utf-8", errors="replace").replace("\r\n", "\n")
                    child_log = Path(temp) / "LabelmeAI.log"
                    log = child_log.read_text(encoding="utf-8", errors="replace") if child_log.is_file() else ""
    except BaseException as error:
        import traceback
        failures.append(traceback.format_exc())
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        if desktop and not user32.CloseDesktop(desktop):
            failures.append(f"CloseDesktop 失败：{c.WinError(c.get_last_error())}")
        code_text = "未知" if exit_status is None else f"{exit_status} ({exit_status:#x})"
        failure_text = "\n".join(failures)
        diagnostic.write_text(
            f"退出码：{code_text}\n异常：{failure_text}\n"
            f"stdout/stderr：\n{output}\n程序日志：\n{log}", encoding="utf-8",
        )
        if sys.stderr is not None:
            sys.stderr.write(output or log)
            if failure_text:
                sys.stderr.write(failure_text + "\n")
    return 0 if exit_status == 0 and not failures else 1


if (
    screenshot_requested and "--screenshot-native" in sys.argv
    and not os.environ.get("LABELME_SCREENSHOT_DESKTOP")
):
    sys.exit(launch_native_screenshot())
if screenshot_requested and "--screenshot-native" in sys.argv:
    print("原生截图阶段：导入正式程序", file=sys.stderr, flush=True)

# 判断是否是 python 启动
if sys.argv[-1].endswith('.py'):
    labelme_path = str(Path(__file__).parent.parent)
    print(f"labelme_path: {labelme_path}")
    sys.path.insert(0, labelme_path)

from labelme.logger import logger  # noqa: F401 先导入logger，防止未正常启动exe就报错

if screenshot_requested:
    sys.excepthook = sys.__excepthook__

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
        help="将界面截图保存到指定目录；完整原生窗口需加 --screenshot-native",
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
        "--screenshot-case", choices=["open", "save", "autosave", "clear", "readonly-save", "reopen", "directory", "invalid-json",
                 "L01-explicit-json", "L01-image-outputdir", "L02-manual-nonstem", "L03-automatic-nonstem",
                 "L04-crossdir-manual", "L05-crossdir-automatic", "L06-valid-empty"],
        default="open", help="在完整副本上执行指定的有限场景（需要 --screenshot-output）",
    )
    parser.add_argument("--screenshot-manifest", type=Path, help="读取指定L01～L06场景的材料与编辑输入，不执行任意动作")
    parser.add_argument("--screenshot-data-root", type=Path, help="包含跨目录图片及 JSON 的完整材料根目录")
    parser.add_argument("--screenshot-filter", choices=["all", "annotated", "unannotated"], default="all",
                        help="目录场景的正式标注状态筛选")
    parser.add_argument(
        "--screenshot-native", action="store_true",
        help="在独立不可见桌面采集完整实际窗口并退出（需要 --screenshot-output）",
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
    if (args.screenshot_case != "open" or args.screenshot_data_root or args.screenshot_manifest or args.screenshot_filter != "all") and args.screenshot_output is None:
        parser.error("场景参数需要 --screenshot-output")
    if args.screenshot_case != "open" and not args.screenshot_native:
        parser.error("新增有限场景需要 --screenshot-native 提供完整原生窗口图")
    if args.screenshot_readonly_save and args.screenshot_clear_group:
        parser.error("只读保存验证不能与整组清空同时使用")
    if args.screenshot_output is not None:
        if (not args.filename and not args.screenshot_manifest) or args.reset_config:
            parser.error("截图模式需要材料路径，且不能与 --reset-config 一起使用")
        # 截图失败直接退出，不弹出等待交互的异常对话框。
        sys.excepthook = sys.__excepthook__
        render_screenshots(
            args.filename, args.screenshot_output, args.screenshot_clear_group,
            readonly_save=args.screenshot_readonly_save, native=args.screenshot_native,
            case=args.screenshot_case, data_root=args.screenshot_data_root,
            output=args.output, filter_mode=args.screenshot_filter, manifest_path=args.screenshot_manifest,
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
    config_from_args.pop("screenshot_case")
    config_from_args.pop("screenshot_data_root")
    config_from_args.pop("screenshot_filter")
    config_from_args.pop("screenshot_manifest")
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




def native_screenshot_desktop():
    """在创建 Qt 主窗前确认专用桌面，拒绝在输入桌面启动截图窗口。"""
    import ctypes as c
    from ctypes import wintypes as w

    if sys.platform != "win32":
        raise RuntimeError("原生完整窗口截图仅支持 Windows")
    user32 = c.WinDLL("user32", use_last_error=True)
    kernel32 = c.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentThreadId.restype = w.DWORD
    kernel32.GetCurrentThreadId.argtypes = []
    user32.GetThreadDesktop.restype = w.HANDLE
    user32.GetThreadDesktop.argtypes = [w.DWORD]
    user32.GetUserObjectInformationW.restype = w.BOOL
    user32.GetUserObjectInformationW.argtypes = [
        w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD),
    ]
    desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    name = c.create_unicode_buffer(256)
    if not user32.GetUserObjectInformationW(desktop, 2, name, c.sizeof(name), None):
        raise c.WinError(c.get_last_error())
    expected = os.environ.get("LABELME_SCREENSHOT_DESKTOP", "")
    if not expected.startswith("LabelmeScreenshot_") or name.value != expected:
        raise RuntimeError(
            f"拒绝采集：当前桌面={name.value}，要求桌面={expected}"
        )
    return name.value


def save_native_screenshot(window, output_dir, name="主窗口.png"):
    """只读取本进程在专用桌面的实际主窗，包含系统标题栏与窗框。"""
    import ctypes as c
    from ctypes import wintypes as w
    import json
    import struct

    from PIL import Image

    user32 = c.WinDLL("user32", use_last_error=True)
    gdi32 = c.WinDLL("gdi32", use_last_error=True)
    dwmapi = c.WinDLL("dwmapi", use_last_error=True)
    pointer = c.c_void_p
    for dll, api_name, result, arguments in (
        (user32, "SetThreadDpiAwarenessContext", pointer, [pointer]),
        (user32, "GetWindowThreadProcessId", w.DWORD, [pointer, c.POINTER(w.DWORD)]),
        (user32, "GetWindowRect", w.BOOL, [pointer, c.POINTER(w.RECT)]),
        (user32, "GetClientRect", w.BOOL, [pointer, c.POINTER(w.RECT)]),
        (user32, "MonitorFromWindow", pointer, [pointer, w.DWORD]),
        (user32, "GetMonitorInfoW", w.BOOL, [pointer, pointer]),
        (dwmapi, "DwmGetWindowAttribute", w.LONG,
         [pointer, w.DWORD, pointer, w.DWORD]),
        (gdi32, "CreateCompatibleDC", pointer, [pointer]),
        (gdi32, "CreateDIBSection", pointer,
         [pointer, pointer, w.UINT, c.POINTER(pointer), pointer, w.DWORD]),
        (gdi32, "SelectObject", pointer, [pointer, pointer]),
        (gdi32, "DeleteObject", w.BOOL, [pointer]),
        (gdi32, "DeleteDC", w.BOOL, [pointer]),
        (gdi32, "GdiFlush", w.BOOL, []),
        (user32, "PrintWindow", w.BOOL, [pointer, pointer, w.UINT]),
    ):
        function = getattr(dll, api_name)
        function.restype = result
        function.argtypes = arguments

    def check(result):
        if not result:
            raise c.WinError(c.get_last_error())
        return result

    def rect_values(rect):
        return [rect.left, rect.top, rect.right, rect.bottom]

    desktop_name = native_screenshot_desktop()
    if QtWidgets.QApplication.instance().platformName() != "windows":
        raise RuntimeError("原生截图需要 Windows Qt 平台")
    hwnd = int(window.winId())
    pid = w.DWORD()
    check(user32.GetWindowThreadProcessId(hwnd, c.byref(pid)))
    if pid.value != os.getpid():
        raise RuntimeError("拒绝采集其他进程的窗口")
    dpi_context = check(user32.SetThreadDpiAwarenessContext(pointer(-4)))
    dc = bitmap = old_bitmap = None
    try:
        rect, client, frame = w.RECT(), w.RECT(), w.RECT()
        check(user32.GetWindowRect(hwnd, c.byref(rect)))
        check(user32.GetClientRect(hwnd, c.byref(client)))
        status = dwmapi.DwmGetWindowAttribute(hwnd, 9, c.byref(frame), c.sizeof(frame))
        if status != 0:
            raise RuntimeError(f"无法读取实际窗框范围：HRESULT={status:#x}")
        # 物理坐标检查只读取实际窗口，不调整位置或尺寸。
        monitor_info = c.create_string_buffer(40)
        struct.pack_into("<I", monitor_info, 0, 40)
        monitor = check(user32.MonitorFromWindow(hwnd, 2))
        check(user32.GetMonitorInfoW(monitor, monitor_info))
        work = struct.unpack_from("<iiii", monitor_info, 20)
        frame_complete = (
            work[0] <= frame.left < frame.right <= work[2]
            and work[1] <= frame.top < frame.bottom <= work[3]
        )
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= client.right or height <= client.bottom:
            raise RuntimeError("实际窗口未包含完整系统窗框与标题栏")
        info = c.create_string_buffer(struct.pack(
            "<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0,
        ) + bytes(4))
        bits = pointer()
        dc = check(gdi32.CreateCompatibleDC(None))
        bitmap = check(gdi32.CreateDIBSection(dc, info, 0, c.byref(bits), None, 0))
        old_bitmap = check(gdi32.SelectObject(dc, bitmap))
        print("原生截图阶段：PrintWindow 捕获", file=sys.stderr, flush=True)
        check(user32.PrintWindow(hwnd, dc, 2))
        check(gdi32.GdiFlush())
        image = Image.frombytes("RGB", (width, height),
                                c.string_at(bits, width * height * 4), "raw", "BGRX")
        final_rect = w.RECT()
        check(user32.GetWindowRect(hwnd, c.byref(final_rect)))
        check(user32.GetWindowThreadProcessId(hwnd, c.byref(pid)))
        if rect_values(final_rect) != rect_values(rect) or pid.value != os.getpid():
            raise RuntimeError("采集期间窗口范围或所属进程发生变化")
        if all(low == high for low, high in image.getextrema()):
            raise RuntimeError("原生捕获返回空白图，未输出截图")
        if not frame_complete:
            failed_image = output_dir / "原生失败原图.png"
            image.save(failed_image)
            raise RuntimeError(
                f"实际窗框超出显示器工作区：window={rect_values(rect)}，"
                f"frame={rect_values(frame)}，work={list(work)}，"
                f"仅保留诊断原图：{failed_image}"
            )
        image.save(output_dir / name)
        metadata_name = "原生截图.json" if name == "主窗口.png" else Path(name).with_suffix(".json").name
        (output_dir / metadata_name).write_text(json.dumps({
            "backend": "PrintWindow", "flags": 2, "pid": pid.value,
            "desktop": desktop_name, "window_rect": rect_values(rect),
            "frame_rect": rect_values(frame), "client_rect": rect_values(client),
            "work_area": list(work), "image_size": list(image.size),
            "theme": (window.parentWidget() if isinstance(window, QtWidgets.QMessageBox) else window).ui_theme_manager.current_theme,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        if old_bitmap:
            gdi32.SelectObject(dc, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if dc:
            gdi32.DeleteDC(dc)
        user32.SetThreadDpiAwarenessContext(dpi_context)



def prepare_screenshot_materials(source, source_root, destination, *, writable):
    """复制完整材料关系，按正式 LabelFile 的路径基准转换绝对引用。"""
    import json
    import shutil

    from qtpy import QtGui
    from labelme.dlcv.label_file import LabelFile, LabelFileError, read_sidecar, _collect_image_paths

    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir() or not source.is_relative_to(source_root):
        raise ValueError("输入材料必须位于指定材料根目录内")
    if destination.resolve().is_relative_to(source_root):
        raise ValueError("截图输出不能位于原始材料根目录内")
    formats = {"." + fmt.data().decode().lower() for fmt in QtGui.QImageReader.supportedImageFormats()}
    files = set()
    annotations = []
    for path in source_root.rglob("*"):
        resolved = path.resolve()
        if not resolved.is_relative_to(source_root):
            raise ValueError(f"材料引用越出指定根目录：{path}")
        if not path.is_file():
            continue
        if path.suffix.lower() in formats or path.suffix.lower() == ".json" or path.name == "label.txt":
            files.add(resolved)
        if path.suffix.lower() != ".json":
            continue
        try:
            label = LabelFile(str(path))
        except (LabelFileError, ValueError, TypeError) as error:
            if writable:
                raise ValueError(f"写入场景不能使用无法解析的标注：{path}：{error}") from error
            continue
        primary = (path.parent / label.imagePath).resolve(strict=writable)
        members = _collect_image_paths(primary, label.otherData, path)
        for member in members:
            member = member.resolve(strict=writable)
            if not member.is_relative_to(source_root):
                raise ValueError(f"标注写入目标越出指定材料根目录：{member}")
            if member.is_file():
                files.add(member)
        annotations.append((path, primary, label))
    if source.is_file():
        files.add(source)
    destination.mkdir()
    for path in sorted(files):
        copied = destination / path.relative_to(source_root)
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copied)
    for path, primary, label in annotations:
        copied = destination / path.relative_to(source_root)
        copied_primary = destination / primary.relative_to(source_root)
        data = read_sidecar(path)
        changed = False
        if Path(label.imagePath).is_absolute():
            data["imagePath"] = os.path.relpath(copied_primary, copied.parent)
            changed = True
        for key, base, copied_base in (
            ("img_name_list", primary.parent, copied_primary.parent),
            ("image_path_list", path.parent, copied.parent),
        ):
            names = label.otherData.get(key)
            if isinstance(names, (list, tuple)):
                rebased = [
                    os.path.relpath(destination / (base / name).resolve().relative_to(source_root), copied_base)
                    if isinstance(name, str) and name and Path(name).is_absolute() else name
                    for name in names
                ]
                if rebased != list(names):
                    data[key] = rebased
                    changed = True
        if changed:
            copied.chmod(copied.stat().st_mode | 0o200)
            copied.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if writable:
        for path, _, _ in annotations:
            copied = destination / path.relative_to(source_root)
            label = LabelFile(str(copied))
            verify_screenshot_targets(
                copied.parent / label.imagePath, copied, label.otherData, destination,
            )
    return destination / source.relative_to(source_root)


def verify_screenshot_targets(primary, sidecar, other_data, material_root):
    """保存、清空前核验正式解析得到的主图、成员及所有外部 JSON 目标。"""
    from labelme.dlcv.label_file import _collect_image_paths

    root = material_root.resolve(strict=True)
    primary = Path(primary).resolve(strict=True)
    sidecar = Path(sidecar).resolve()
    members = _collect_image_paths(primary, other_data, sidecar)
    for path in [sidecar, primary, *members, *(Path(member).with_suffix(".json") for member in members)]:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"拒绝操作副本之外的写入目标：{resolved}")
    for member in members:
        if not Path(member).is_file():
            raise FileNotFoundError(member)
    return [Path(member).resolve() for member in members]


def render_screenshots(filename, output_dir, clear_group=False, *, readonly_save=False,
                       native=False, case="open", data_root=None, output=None, filter_mode="all", manifest_path=None):
    """在完整材料副本上执行有限的正式界面场景，不启动外部服务。"""
    import json
    import stat
    import tempfile

    from qtpy import QtGui
    from labelme.dlcv import dlcv_tr
    from labelme.dlcv.store import STORE
    from labelme.dlcv.label_file import LabelFile, read_sidecar
    from dlcv_core.image_json import has_image_json, read_image_json

    if native:
        native_screenshot_desktop()
    if clear_group:
        case = "clear"
    if readonly_save:
        case = "readonly-save"
    fixed_sequences = {
        "L01-explicit-json": ("open_json", "import_images", "filter_annotated", "filter_unannotated", "count_directory"),
        "L01-image-outputdir": ("open_image", "import_images", "count_directory"),
        "L02-manual-nonstem": ("open_json", "edit_shape", "manual_save", "reopen_json"),
        "L03-automatic-nonstem": ("open_json", "set_auto_save", "edit_shape", "edit_shape", "reopen_json"),
        "L04-crossdir-manual": ("open_json", "edit_shape", "save_as", "edit_shape", "manual_save", "reopen_json",
                              "set_auto_save", "clear_all_shapes_and_flags", "manual_save", "reopen_image"),
        "L05-crossdir-automatic": ("open_json", "edit_shape", "save_as", "set_auto_save", "edit_shape", "edit_shape",
                                 "reopen_json", "set_auto_save", "clear_all_shapes_and_flags", "manual_save", "reopen_image"),
        "L06-valid-empty": ("open_image", "open_image"),
    }
    case_spec = None
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        matches = [item for item in manifest["cases"] if item["id"] == case]
        if manifest["schema_version"] != 1 or case not in fixed_sequences or len(matches) != 1:
            raise ValueError("材料仅支持已确认的L01～L06有限场景")
        case_spec = matches[0]
        if tuple(step["action"] for step in case_spec["steps"]) != fixed_sequences[case]:
            raise ValueError("材料步骤不属于该有限场景；不会解释任意动作")
        fixture_root = Path(case_spec["fixture_root"]).resolve(strict=True)
        if data_root and Path(data_root).resolve(strict=True) != fixture_root:
            raise ValueError("指定材料根目录与该场景fixture_root不一致")
        data_root = fixture_root
        inputs = case_spec["inputs"]
        initial = inputs["previous_image"] if case == "L06-valid-empty" else (
            inputs["image"] if case == "L01-image-outputdir" else inputs["selected_json"]
        )
        expected_input = (fixture_root / initial).resolve(strict=True)
        if filename and Path(filename).resolve(strict=True) != expected_input:
            raise ValueError("材料路径与该有限场景的正式输入不一致")
        filename = str(expected_input)
        if output is None:
            output = inputs.get("output_dir")
    elif case in fixed_sequences:
        raise ValueError("L01～L06场景需要--screenshot-manifest")
    writable = case in ("save", "autosave", "clear", "readonly-save",
                        "L02-manual-nonstem", "L03-automatic-nonstem", "L04-crossdir-manual", "L05-crossdir-automatic")
    source = Path(filename).resolve(strict=True)
    source_root = Path(data_root).resolve(strict=True) if data_root else (
        source if source.is_dir() else source.parent
    )
    output_dir = Path(output_dir).resolve(strict=True)
    if not output_dir.is_dir():
        raise NotADirectoryError(output_dir)
    material_root = output_dir / "材料副本"
    image_names = ("主窗口.png", "设置面板.png", "标注页.png", "错误提示.png",
                   "保存前主窗口.png", "保存后主窗口.png", "清空前主窗口.png", "重开主窗口.png",
                   "初始主窗口.png", "已标注筛选主窗口.png", "未标注筛选主窗口.png",
                   "导入目录后主窗口.png", "目录统计主窗口.png", "目录文本标记统计主窗口.png", "目录标签统计主窗口.png",
                   "目录总数主窗口.png", "目录导入确认.png", "手动保存后主窗口.png",
                   "自动第一次主窗口.png", "自动第二次主窗口.png", "另存后主窗口.png",
                   "连续保存后主窗口.png", "清空后主窗口.png", "主图重开窗口.png", "合法空标注主窗口.png")
    result_path = output_dir / "场景结果.json"
    reserved = (*image_names, *(Path(name).with_suffix(".json").name for name in image_names),
                "原生截图.json", "场景结果.json", "只读保存验证.json", "清空验证.json")
    if material_root.exists() or any((output_dir / name).exists() for name in reserved):
        raise FileExistsError("场景输出已存在，请使用新的空目录")
    result = {"case": case, "success": False, "material_root": str(material_root)}
    if case_spec:
        result["manifest"] = str(manifest_path)
    win = None
    protected_image = None
    settings_directory = None
    BaseMainWindow = globals()["MainWindow"]

    class MainWindow(BaseMainWindow):
        # 正式构造器多次创建 NativeFormat，截图实例始终使用同一份隔离 INI。
        @property
        def settings(self):
            return screenshot_settings

        @settings.setter
        def settings(self, value):
            pass

        @property
        def dev_setting(self):
            return screenshot_dev_settings

        @dev_setting.setter
        def dev_setting(self, value):
            pass

        def __init__(self, *args, **kwargs):
            self.screenshot_errors = []
            self.screenshot_capture_errors = []
            self.settings = screenshot_settings
            STORE.register_main_window(self)
            dlcv_tr("设置面板")
            super().__init__(*args, **kwargs)

        def _init_dlcv_ai_widget(self):
            pass

        def mayContinue(self):
            if case not in ("L01-explicit-json", "L01-image-outputdir") or not self.dirty:
                return super().mayContinue()

            def discard_import_changes():
                dialog = QtWidgets.QApplication.activeModalWidget()
                buttons = QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel
                if (not isinstance(dialog, QtWidgets.QMessageBox) or dialog.parentWidget() is not self
                        or dialog.standardButtons() != buttons
                        or dialog.windowTitle() != self.tr("Save annotations?")):
                    self.screenshot_capture_errors.append("目录导入的正式保存确认未进入预期状态")
                    if isinstance(dialog, QtWidgets.QMessageBox) and dialog.parentWidget() is self:
                        dialog.reject()
                    return
                self.screenshot_import_dialog = dialog
                try:
                    save_native_screenshot(dialog, output_dir, "目录导入确认.png")
                    # 固定只读导入选择正式 Discard，不调用保存或输入模拟。
                    dialog.button(QtWidgets.QMessageBox.Discard).click()
                except Exception as error:
                    self.screenshot_capture_errors.append(str(error))
                    dialog.reject()

            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(discard_import_changes)
            timer.start(700)
            try:
                return super().mayContinue()
            finally:
                timer.stop()
                timer.deleteLater()
                self.screenshot_import_dialog = None

        def errorMessage(self, title, message):
            self.screenshot_errors.append({"title": str(title), "message": str(message)})
            dialog = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Critical, title, "<p><b>%s</b></p>%s" % (title, message),
                QtWidgets.QMessageBox.Ok, self,
            )

            def capture_error():
                if native and QtWidgets.QApplication.activeModalWidget() is not dialog:
                    self.screenshot_capture_errors.append("正式错误对话框未进入可采集状态")
                    dialog.done(QtWidgets.QMessageBox.Cancel)
                    return
                try:
                    if native:
                        save_native_screenshot(dialog, output_dir, "错误提示.png")
                    else:
                        image = QtGui.QImage(dialog.size(), QtGui.QImage.Format_ARGB32)
                        image.fill(QtGui.QColor("white"))
                        dialog.render(image)
                        if not image.save(str(output_dir / "错误提示.png")):
                            raise RuntimeError("错误对话框绘制失败")
                except Exception as error:
                    self.screenshot_capture_errors.append(str(error))
                finally:
                    dialog.done(QtWidgets.QMessageBox.Ok)

            timer = QtCore.QTimer(dialog)
            timer.setSingleShot(True)
            timer.timeout.connect(capture_error)
            try:
                if native:
                    timer.start(700)
                    return dialog.exec_()
                # Qt 5.15 Windows 的 QMessageBox.showEvent 会解引用 offscreen 不具备的原生接口。
                dialog.ensurePolished()
                dialog.adjustSize()
                capture_error()
                return QtWidgets.QMessageBox.Ok
            finally:
                timer.stop()
                dialog.deleteLater()

    try:
        copied = prepare_screenshot_materials(source, source_root, material_root, writable=writable)
        requested_output = None
        if output:
            requested = Path(output)
            requested = requested.resolve() if requested.is_absolute() else (source_root / requested).resolve()
            if not requested.is_relative_to(source_root):
                raise ValueError("--output 必须位于材料根目录内；截图模式会映射到副本")
            requested_output = material_root / requested.relative_to(source_root)
            requested_output.parent.mkdir(parents=True, exist_ok=True)
            if requested_output.suffix.lower() != ".json":
                requested_output.mkdir(parents=True, exist_ok=True)
        def material_path(relative, *, existing=False):
            candidate = (material_root / relative).resolve(strict=existing)
            if not candidate.is_relative_to(material_root.resolve()):
                raise ValueError(f"场景路径不在完整副本内：{relative}")
            return candidate

        if case_spec:
            for key in ("image", "selected_json", "previous_image", "output_dir", "images_directory", "save_as_json"):
                if key in case_spec["inputs"]:
                    material_path(case_spec["inputs"][key])
            for member in case_spec["inputs"].get("member_images", []):
                material_path(member, existing=True)

        result.update(input=str(copied), requested_output=str(requested_output) if requested_output else None)
        settings_directory = tempfile.TemporaryDirectory(prefix="labelme-ui-", ignore_cleanup_errors=True)
        temp_path = Path(settings_directory.name)
        for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
            os.environ[key] = str(temp_path)
        screenshot_settings = QtCore.QSettings(str(temp_path / "labelme.ini"), QtCore.QSettings.IniFormat)
        screenshot_dev_settings = QtCore.QSettings(str(temp_path / "dev.ini"), QtCore.QSettings.IniFormat)
        screenshot_settings.setValue("ui/theme", "modern")
        if case_spec and "save_external_json" in case_spec["settings"]:
            screenshot_settings.setValue("setting_store", {"save_external_json": case_spec["settings"]["save_external_json"]})
        if native:
            screenshot_settings.setValue("window/position", QtCore.QPoint(32, 32))
        screenshot_settings.sync()
        if screenshot_settings.status() != QtCore.QSettings.NoError:
            raise RuntimeError("截图实例的隔离 INI 启动配置写入失败")
        result["settings_file"] = screenshot_settings.fileName()
        print(f"截图启动配置：{screenshot_settings.fileName()}，position={screenshot_settings.value('window/position')}",
              file=sys.stderr, flush=True)
        config = get_config(str(temp_path / ".labelmerc"), {})
        # 副本加载阶段不保存；自动保存场景仅在写目标核验之后启用。
        config["auto_save"] = False
        if case_spec:
            config["keep_prev"] = case_spec["settings"]["keep_prev"]
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
        output_file = str(requested_output) if requested_output and requested_output.suffix.lower() == ".json" else None
        output_folder = str(requested_output) if requested_output and not output_file else None
        win = MainWindow(config=config, filename=None, output_file=output_file, output_dir=output_folder)
        if not native:
            win.resize(1920, 1080)
        win.show()
        for _ in range(5):
            app.processEvents()
        if dlcv_tr.get_lang() != "zh_CN" or translator.isEmpty() or win.file_dock.windowTitle() != "文件列表":
            raise RuntimeError("正式主窗中文翻译未加载")

        def capture(widget, name):
            if native:
                settle = QtCore.QEventLoop()
                QtCore.QTimer.singleShot(700, settle.quit)
                settle.exec_()
                save_native_screenshot(widget, output_dir, name)
            else:
                image = QtGui.QImage(widget.size(), QtGui.QImage.Format_ARGB32)
                image.fill(QtGui.QColor("white"))
                widget.render(image)
                if not image.save(str(output_dir / name)):
                    raise RuntimeError(f"界面绘制失败：{name}")

        if case_spec:
            image_directory = material_path(case_spec["inputs"]["images_directory"], existing=True) if "images_directory" in case_spec["inputs"] else material_root
            if case not in ("L01-explicit-json", "L01-image-outputdir"):
                win.importDirImages(str(image_directory), load=False)
        else:
            win.importDirImages(str(material_root), load=False)
        open_path = copied
        if copied.is_dir():
            paths = list(win.imageList or [])
            open_path = Path(paths[0]) if paths else None
        loaded = bool(open_path and win.loadFile(str(open_path)))
        app.processEvents()
        if case != "invalid-json" and case != "directory" and (not loaded or win.image.isNull()):
            raise RuntimeError("输入材料未能通过正式主窗加载")
        result["loaded"] = loaded
        result["before_labels"] = [shape.label for shape in win.canvas.shapes]
        result["before_image"] = win.filename

        def write_targets():
            label = win.labelFile
            loaded_sidecar = getattr(label, "sidecar_path", None)
            sidecar = loaded_sidecar or win.getLabelFile()
            target = requested_output if output_file else Path(sidecar)
            primary = Path(sidecar).parent / label.imagePath if label else Path(win.filename)
            members = verify_screenshot_targets(primary, sidecar, win.otherData, material_root)
            verify_screenshot_targets(primary, target, {}, material_root)
            if not Path(win.imagePath).resolve().is_relative_to(material_root.resolve()):
                raise ValueError(f"当前图像写入目标不在副本内：{win.imagePath}")
            for name in win.proj_manager.get_img_name_list(win.filename):
                member = (Path(win.filename).parent / name).resolve()
                if not member.is_relative_to(material_root.resolve()) or not member.is_file():
                    raise ValueError(f"项目图片成员不在完整副本内：{member}")
            return primary.resolve(), Path(target), members

        if case_spec:
            import shutil
            from PIL import Image

            inputs, steps = case_spec["inputs"], case_spec["steps"]
            original_pixels = {}
            for image_path in material_root.rglob("*.png"):
                with Image.open(image_path) as image:
                    original_pixels[str(image_path.relative_to(material_root))] = (image.mode, image.size, image.tobytes())
            result["stages"] = []

            def checkpoint(name):
                capture(win, name + ".png")
                snapshot_root = output_dir / "阶段材料" / name
                snapshot_root.parent.mkdir(exist_ok=True)
                shutil.copytree(material_root, snapshot_root)
                pixels = {}
                for relative, original in original_pixels.items():
                    with Image.open(material_path(relative, existing=True)) as image:
                        pixels[relative] = {"size": list(image.size), "unchanged": (image.mode, image.size, image.tobytes()) == original}
                flags = {}
                for index in range(win.flag_widget.count()):
                    item = win.flag_widget.item(index)
                    flags[item.text()] = item.checkState() == QtCore.Qt.Checked
                active = getattr(win.labelFile, "sidecar_path", None)
                result["stages"].append({
                    "name": name, "material_root": str(snapshot_root), "screenshot": str(output_dir / (name + ".png")),
                    "active_json": str(snapshot_root / Path(active).resolve().relative_to(material_root.resolve())) if active else None,
                    "working_json": str(active), "displayed_image": win.filename,
                    "canvas_shapes": [{"label": shape.label, "points": [[point.x(), point.y()] for point in shape.points],
                                       "shape_type": shape.shape_type, "flags": shape.flags, "group_id": shape.group_id,
                                       "description": shape.description, "other_data": shape.other_data} for shape in win.canvas.shapes],
                    "flags": flags, "pixels": pixels,
                })
                if not all(item["unchanged"] for item in pixels.values()):
                    raise RuntimeError("实际图片像素或尺寸变化，场景未通过")

            def edit_shape(step):
                write_targets()
                shape = win.canvas.shapes[step["index"]]
                shape.points = [QtCore.QPointF(x, y) for x, y in step["points"]]
                win._update_item(win.labelList.findItemByShape(shape), step["label"], None, None, None)
                win.canvas.update()

            checkpoint("初始主窗口")
            if case in ("L01-explicit-json", "L01-image-outputdir"):
                win.importDirImages(str(image_directory), load=False)
                if not win.lastOpenDir or Path(win.lastOpenDir).resolve() != image_directory.resolve():
                    raise RuntimeError("正式目录导入未完成")
                checkpoint("导入目录后主窗口")
                if case == "L01-explicit-json":
                    win.fileListWidget.show_annotated_checkbox.setChecked(True)
                    checkpoint("已标注筛选主窗口")
                    win.fileListWidget.show_annotated_checkbox.setChecked(False)
                    win.fileListWidget.show_unannotated_checkbox.setChecked(True)
                    checkpoint("未标注筛选主窗口")
                    win.fileListWidget.show_unannotated_checkbox.setChecked(False)
                win.label_count_dock.count_labels_in_dir()
                result["statistics"] = win.label_count_dock.label_count_text.toPlainText()
                checkpoint("目录统计主窗口")
                statistics_view = win.label_count_dock.label_count_text
                for heading, name in (("文本标记统计:", "目录文本标记统计主窗口"), ("标签统计:", "目录标签统计主窗口")):
                    cursor = statistics_view.document().find(heading)
                    if cursor.isNull():
                        raise RuntimeError(f"实际目录统计未显示{heading}")
                    cursor.movePosition(QtGui.QTextCursor.NextBlock, QtGui.QTextCursor.MoveAnchor, 2)
                    statistics_view.setTextCursor(cursor)
                    statistics_view.ensureCursorVisible()
                    checkpoint(name)
                win.label_count_dock.label_count_text.moveCursor(QtGui.QTextCursor.End)
                checkpoint("目录总数主窗口")
            elif case == "L02-manual-nonstem":
                edit_shape(steps[1])
                if not win.saveFile():
                    raise RuntimeError("非同名JSON正式手动保存失败")
                checkpoint("手动保存后主窗口")
                if not win.loadFile(str(material_path(inputs["selected_json"], existing=True))):
                    raise RuntimeError("选定JSON重开失败")
                checkpoint("重开主窗口")
            elif case == "L03-automatic-nonstem":
                write_targets()
                win._config["auto_save"] = True
                win.actions.saveAuto.setChecked(True)
                edit_shape(steps[2])
                checkpoint("自动第一次主窗口")
                edit_shape(steps[3])
                checkpoint("自动第二次主窗口")
                if not win.loadFile(str(material_path(inputs["selected_json"], existing=True))):
                    raise RuntimeError("自动保存后选定JSON重开失败")
                checkpoint("重开主窗口")
            elif case in ("L04-crossdir-manual", "L05-crossdir-automatic"):
                edit_shape(steps[1])
                save_as = material_path(inputs["save_as_json"])
                primary, _, _ = write_targets()
                verify_screenshot_targets(primary, save_as, {}, material_root)
                if not win._saveFile(str(save_as)):
                    raise RuntimeError("跨目录正式另存失败")
                checkpoint("另存后主窗口")
                if case == "L04-crossdir-manual":
                    edit_shape(steps[3])
                    if not win.saveFile():
                        raise RuntimeError("跨目录续存失败")
                    checkpoint("连续保存后主窗口")
                else:
                    write_targets()
                    win._config["auto_save"] = True
                    win.actions.saveAuto.setChecked(True)
                    edit_shape(steps[4])
                    checkpoint("自动第一次主窗口")
                    edit_shape(steps[5])
                    checkpoint("自动第二次主窗口")
                if not win.loadFile(str(save_as)):
                    raise RuntimeError("跨目录新JSON重开失败")
                checkpoint("重开主窗口")
                win._config["auto_save"] = False
                win.actions.saveAuto.setChecked(False)
                write_targets()
                win.canvas.selectShapes(win.canvas.shapes)
                win.deleteSelectedShape()
                win.loadFlags({})
                write_targets()
                if not win.saveFile():
                    raise RuntimeError("跨目录整组清空失败")
                checkpoint("清空后主窗口")
                if not win.loadFile(str(material_path(inputs["image"], existing=True))):
                    raise RuntimeError("清空后主图重开失败")
                checkpoint("主图重开窗口")
            elif case == "L06-valid-empty":
                if not win.loadFile(str(material_path(inputs["image"], existing=True))):
                    raise RuntimeError("keep_prev场景合法空标注图片打开失败")
                win.fileListWidget.expandAll()
                checkpoint("合法空标注主窗口")
                if win.canvas.shapes:
                    raise RuntimeError("keep_prev覆盖了合法空JSON的空标注")
            result["success"] = not win.screenshot_errors
        elif writable:
            primary, target, members = write_targets()
            result["write_targets"] = [str(path) for path in members] + [str(target)]
            if case == "readonly-save":
                protected_image = primary
                before_bytes = primary.read_bytes()
                primary.chmod(stat.S_IREAD)
                if not win.canvas.shapes:
                    raise ValueError("只读保存场景需要已有标注")
                win._update_item(win.labelList.findItemByShape(win.canvas.shapes[0]), "未保存验证", None, None, None)
                saved = win.saveLabels(str(target))
                readonly_result = {
                    "save_returned": saved, "edited_label": win.canvas.shapes[0].label,
                    "image_unchanged": primary.read_bytes() == before_bytes,
                    "image_readonly": not bool(primary.stat().st_mode & stat.S_IWRITE),
                    "embedded_annotation": read_image_json(primary), "dirty": win.dirty,
                    "errors": [error["message"] for error in win.screenshot_errors],
                }
                readonly_result["success"] = bool(not saved and win.dirty and win.screenshot_errors and readonly_result["image_unchanged"])
                (output_dir / "只读保存验证.json").write_text(json.dumps(readonly_result, ensure_ascii=False, indent=2), encoding="utf-8")
                result.update(readonly_result)
            elif case == "clear":
                capture(win, "清空前主窗口.png")
                win.canvas.selectShapes(win.canvas.shapes)
                win.deleteSelectedShape()
                win.loadFlags({})
                write_targets()
                saved = win.saveLabels(str(target))
                states = []
                for member in members:
                    reopened = bool(win.loadFile(str(member)))
                    items = win.fileListWidget.findItems(str(member))
                    states.append({
                        "name": str(member.relative_to(material_root)),
                        "embedded_json_exists": has_image_json(member),
                        "external_json_exists": member.with_suffix(".json").exists(),
                        "reopened_label_count": len(win.canvas.shapes),
                        "has_label_file": win.hasLabelFile(),
                        "file_tree_checked": any(item.checkState(0) != QtCore.Qt.Unchecked for item in items),
                        "success": reopened and not win.canvas.shapes and not has_image_json(member)
                                   and not member.with_suffix(".json").exists(),
                    })
                result.update(save_returned=saved, images=states)
                result["success"] = bool(saved and states and all(item["success"] for item in states))
                (output_dir / "清空验证.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                win.loadFile(str(primary))
            else:
                capture(win, "保存前主窗口.png")
                if case == "autosave":
                    win._config["auto_save"] = True
                    win.actions.saveAuto.setChecked(True)
                if not win.canvas.shapes:
                    win.loadLabels([{
                        "label": "保存验证", "points": [[10, 10], [30, 30]], "shape_type": "rectangle",
                        "flags": {}, "group_id": None, "other_data": {}, "mask": None,
                    }])
                win._update_item(win.labelList.findItemByShape(win.canvas.shapes[0]), "保存验证", None, None, None)
                saved = not win.dirty if case == "autosave" else win.saveLabels(str(target))
                actual_sidecar = Path(win.labelFile.sidecar_path) if win.labelFile else target
                verify_screenshot_targets(primary, actual_sidecar, win.otherData, material_root)
                external = read_sidecar(actual_sidecar)
                embedded = {}
                for member in members:
                    data = read_image_json(member)
                    embedded[str(member)] = {
                        "exists": data is not None,
                        "labels": [shape.get("label") for shape in (data or {}).get("shapes", [])],
                    }
                result.update(save_returned=saved, saved_json=str(actual_sidecar),
                              external_labels=[shape.get("label") for shape in external.get("shapes", [])],
                              embedded_images=embedded)
                result["success"] = bool(saved and any(shape.get("label") == "保存验证" for shape in external.get("shapes", [])))
                capture(win, "保存后主窗口.png")
                win._config["auto_save"] = False
                win.actions.saveAuto.setChecked(False)
                reopened = bool(win.loadFile(str(actual_sidecar)))
                result["reopened"] = reopened
                result["success"] = result["success"] and reopened and any(shape.label == "保存验证" for shape in win.canvas.shapes)
                capture(win, "重开主窗口.png")
        elif case == "reopen":
            first_labels = [shape.label for shape in win.canvas.shapes]
            reopened = bool(win.loadFile(str(open_path)))
            result.update(reopened=reopened, success=reopened and first_labels == [shape.label for shape in win.canvas.shapes])
            capture(win, "重开主窗口.png")
        elif case == "directory":
            win.fileListWidget.show_annotated_checkbox.setChecked(filter_mode == "annotated")
            win.fileListWidget.show_unannotated_checkbox.setChecked(filter_mode == "unannotated")
            win.label_count_dock.count_labels_in_dir()
            visible = []
            for path in win.imageList or []:
                if any(not item.isHidden() for item in win.fileListWidget.findItems(str(path))):
                    visible.append(str(path))
            result.update(filter=filter_mode, visible_images=visible,
                          statistics=win.label_count_dock.label_count_text.toPlainText(), success=True)
        elif case == "invalid-json":
            result["success"] = bool(win.screenshot_errors and (output_dir / "错误提示.png").is_file())
        else:
            result["success"] = loaded and not win.screenshot_errors
        result.update(labels=[shape.label for shape in win.canvas.shapes],
                      displayed_image=win.filename, errors=win.screenshot_errors,
                      dialog_capture_errors=win.screenshot_capture_errors)
        if win.screenshot_capture_errors:
            result["success"] = False
        capture(win, "主窗口.png")
        if not native:
            capture(win.canvas, "标注页.png")
            for dock in (win.flag_dock, win.label_dock, win.shape_dock, win.label_count_dock):
                dock.hide()
            app.processEvents()
            capture(win.setting_dock, "设置面板.png")
        if not result["success"]:
            raise RuntimeError("正式场景未通过，详见场景结果.json与实际程序图片")
    except BaseException as error:
        result["success"] = False
        result["failure"] = str(error)
        raise
    finally:
        try:
            if win is not None:
                result["errors"] = win.screenshot_errors
                win._config["auto_save"] = False
                win.actions.saveAuto.setChecked(False)
                win.setClean()
                win.close()
                win.settings.sync()
                win.dev_setting.sync()
                if any(settings.status() != QtCore.QSettings.NoError for settings in (win.settings, win.dev_setting)):
                    raise RuntimeError("正式关闭后的隔离 INI 保存失败")
                QtWidgets.QApplication.instance().processEvents()
            if protected_image is not None and protected_image.is_file():
                protected_image.chmod(stat.S_IREAD | stat.S_IWRITE)
        except BaseException as error:
            result["success"] = False
            result["failure"] = str(error)
            raise
        finally:
            try:
                result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            finally:
                STORE.q_translator = None
                if settings_directory is not None:
                    settings_directory.cleanup()


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
