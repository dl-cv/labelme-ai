"""正式截图入口、专用桌面与采集参数回归。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


def test_offscreen_capture_uses_real_annotation(tmp_path):
    sample = (
        Path(__file__).resolve().parents[3]
        / "examples" / "instance_segmentation" / "data_annotated"
        / "2011_000003.jpg"
    )
    original = (sample.stat().st_size, sample.stat().st_mtime_ns)
    annotation = sample.with_suffix(".json")
    original_annotation = (annotation.stat().st_size, annotation.stat().st_mtime_ns)
    assert sample.is_file() and annotation.is_file()
    output = tmp_path / "screenshots"
    output.mkdir()
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    result = subprocess.run(
        [sys.executable, "-m", "labelme", "--screenshot-output",
         str(output), str(sample)],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "当前语言设置为: zh_CN" in result.stdout
    assert (sample.stat().st_size, sample.stat().st_mtime_ns) == original
    assert (
        annotation.stat().st_size, annotation.stat().st_mtime_ns
    ) == original_annotation
    assert {file.name for file in output.iterdir()} == {
        "主窗口.png", "设置面板.png", "标注页.png", "场景结果.json", "材料副本"
    }
    report = json.loads((output / "场景结果.json").read_text(encoding="utf-8"))
    expected = json.loads(annotation.read_text(encoding="utf-8"))
    assert report["success"] and report["loaded"]
    assert report["labels"] == [shape["label"] for shape in expected["shapes"]]
    for file in output.glob("*.png"):
        with Image.open(file) as image:
            assert image.size[0] > 200 and image.size[1] > 200
            assert image.getbbox() is not None
            if file.name == "主窗口.png":
                assert image.size == (1920, 1080)


def test_offscreen_capture_clears_two_image_group(tmp_path):
    from labelme.dlcv.label_file import LabelFile

    repository = Path(__file__).resolve().parents[3]
    sample = (
        repository / "examples" / "instance_segmentation" / "data_annotated"
        / "2011_000003.jpg"
    )
    annotation = json.loads(sample.with_suffix(".json").read_text(encoding="utf-8"))
    materials = tmp_path / "materials"
    materials.mkdir()
    images = [materials / name for name in ("first.jpg", "second.jpg")]
    for image in images:
        shutil.copy2(sample, image)
    for image in images:
        LabelFile().save(
            filename=str(image.with_suffix(".json")),
            shapes=annotation["shapes"][:1], imagePath=image.name,
            imageHeight=annotation["imageHeight"], imageWidth=annotation["imageWidth"],
            flags={}, otherData={
                "image_path_list": ["first.jpg"], "img_name_list": ["second.jpg"],
            }, save_external_json=True,
        )
    originals = {path: path.read_bytes() for path in materials.iterdir()}
    assert len(originals) == 4
    output = tmp_path / "screenshots"
    output.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    env.update({"TEMP": str(runtime), "TMP": str(runtime),
                "LABELME_LOG_DIR": str(runtime)})
    result = subprocess.run(
        [sys.executable, "-m", "labelme", "--screenshot-output", str(output),
         "--screenshot-clear-group", str(images[0])],
        cwd=repository, env=env, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {path: path.read_bytes() for path in materials.iterdir()} == originals
    assert {path.name for path in output.iterdir()} == {
        "主窗口.png", "设置面板.png", "标注页.png", "清空前主窗口.png", "清空验证.json", "场景结果.json", "材料副本",
    }
    report = json.loads((output / "清空验证.json").read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["images"] == [
            {
                "name": name, "reopened_label_count": 0,
                "embedded_json_exists": False, "external_json_exists": False,
                "has_label_file": False, "file_tree_checked": False, "success": True,
            }
            for name in ("first.jpg", "second.jpg")
        ]
    for name in ("清空前主窗口.png", "主窗口.png"):
        with Image.open(output / name) as image:
            assert image.size == (1920, 1080)
            assert image.getbbox() is not None


def test_offscreen_readonly_save_keeps_failure_and_dirty_edits(tmp_path):
    """正式主窗内嵌写入失败时保留编辑，外部备份不能改判成功。"""
    if os.name != "nt":
        import pytest
        pytest.skip("使用 Windows 只读文件属性")
    repository = Path(__file__).resolve().parents[3]
    sample = repository / "examples/instance_segmentation/data_annotated/2011_000003.jpg"
    original = sample.read_bytes()
    output = tmp_path / "screenshots"
    output.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "labelme", "--screenshot-output", str(output),
         "--screenshot-readonly-save", str(sample)],
        cwd=repository, env=os.environ.copy(), capture_output=True, text=True,
        encoding="utf-8", timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "只读保存验证.json").read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["save_returned"] is False
    assert report["edited_label"] == "未保存验证"
    assert report["embedded_annotation"] is None
    assert report["image_unchanged"]
    assert report["dirty"] is True
    assert report["errors"] and "Permission denied" in report["errors"][0]
    assert sample.read_bytes() == original


@pytest.mark.parametrize("arguments", [
    ["--screenshot-native"], ["--screenshot-readonly-save"], ["--screenshot-clear-group"],
    ["--screenshot-output", "output"],
    ["sample.jpg", "--screenshot-output", "output", "--reset-config"],
    ["sample.jpg", "--screenshot-output", "output", "--screenshot-readonly-save", "--screenshot-clear-group"],
    ["sample.jpg", "--screenshot-case", "save"],
    ["sample.jpg", "--screenshot-data-root", "materials"],
    ["sample.jpg", "--screenshot-filter", "annotated"],
    ["sample.jpg", "--screenshot-case", "unsupported"],
    ["sample.jpg", "--screenshot-output", "output", "--screenshot-case", "save"],
])
def test_screenshot_cli_rejects_invalid_parameter_combinations(monkeypatch, arguments):
    from labelme import __main__ as entrypoint

    monkeypatch.setattr(sys, "argv", ["labelme", *arguments])
    with pytest.raises(SystemExit) as error:
        entrypoint.main()
    assert error.value.code == 2


def test_screenshot_cli_accepts_equals_output_parameter(monkeypatch, tmp_path):
    from labelme import __main__ as entrypoint

    calls = []
    monkeypatch.setattr(sys, "argv", ["labelme", "sample.jpg", f"--screenshot-output={tmp_path}", "--screenshot-native"])
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(entrypoint, "render_screenshots", lambda *args, **kwargs: calls.append((args, kwargs)))
    entrypoint.main()
    assert calls == [(("sample.jpg", tmp_path, False), {"readonly_save": False, "native": True, "case": "open", "data_root": None, "output": None, "filter_mode": "all", "manifest_path": None})]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用桌面入口")
@pytest.mark.parametrize("failure", [None, "timeout", "interrupt", "child_failed", "create_failed", "terminate_failed", "exit_failed", "unknown_exit", "wait_failed", "thread_close_failed", "process_close_failed", "desktop_close_failed"])
def test_native_launcher_cleans_only_owned_process_and_desktop(monkeypatch, tmp_path, capsys, failure):
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace
    from labelme import __main__ as entrypoint

    events, received = [], {"running": True}
    raw_exit = 0xC0000005 if failure == "child_failed" else 259 if failure == "unknown_exit" else 0 if failure in ("exit_failed", "thread_close_failed", "process_close_failed", "desktop_close_failed") else 1 if failure else 0
    def create_desktop(name, device, mode, flags, access, security):
        received.update(desktop=name, access=access)
        events.append(("create", 101))
        return 101
    def close_desktop(handle):
        events.append(("desktop-close", handle))
        return 0 if failure == "desktop_close_failed" else 1
    def create_process(executable, command_line, process_security, thread_security, inherit, flags, environment, cwd, startup, process):
        info = startup._obj
        received.update(executable=executable, command=command_line.value, flags=flags,
            desktop_from_startup=info.lpDesktop, startup_size=info.cb, startup_fields=type(info)._fields_,
            std_handles=(info.hStdInput, info.hStdOutput, info.hStdError), startup_flags=info.dwFlags,
            env=dict(part.split("=", 1) for part in environment[:].split("\0") if part), inherit=inherit)
        assert isinstance(info, ctypes.Structure)
        assert os.get_handle_inheritable(info.hStdInput)
        assert os.get_handle_inheritable(info.hStdOutput)
        events.append(("start", 301))
        if failure == "create_failed":
            return 0
        process._obj.hProcess, process._obj.hThread = 301, 302
        home = Path(received["env"]["HOME"])
        (home / "子进程输出.txt").write_text("模拟子进程输出\n", encoding="utf-8")
        (home / "LabelmeAI.log").write_text("模拟程序日志\n", encoding="utf-8")
        return 1
    def wait(handle, milliseconds):
        assert handle == 301
        events.append(("wait", milliseconds))
        if milliseconds == 45000:
            if failure == "interrupt":
                raise KeyboardInterrupt
            if failure in ("timeout", "terminate_failed"):
                return 0x102
            if failure == "wait_failed":
                return 0xFFFFFFFF
            received["running"] = False
        return 0x102 if received["running"] else 0
    def terminate(handle, code):
        assert handle == 301 and code == 1
        events.append(("terminate", handle))
        if failure == "terminate_failed":
            return 0
        received["running"] = False
        return 1
    def exit_code(handle, target):
        assert handle == 301
        target._obj.value = raw_exit
        return 0 if failure == "exit_failed" else 1
    def close_handle(handle):
        events.append(("handle-close", handle))
        return 0 if (failure == "thread_close_failed" and handle == 302) or (failure == "process_close_failed" and handle == 301) else 1
    apis = {"user32": SimpleNamespace(CreateDesktopW=create_desktop, CloseDesktop=close_desktop),
            "kernel32": SimpleNamespace(CreateProcessW=create_process, WaitForSingleObject=wait,
                GetExitCodeProcess=exit_code, TerminateProcess=terminate, CloseHandle=close_handle)}
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: apis[name])
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)
    argv = ["labelme", "sample.jpg", f"--screenshot-output={tmp_path}", "--screenshot-native"]
    monkeypatch.setattr(sys, "argv", argv)
    if failure == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            entrypoint.launch_native_screenshot()
    else:
        assert entrypoint.launch_native_screenshot() == (0 if failure is None else 1)
    command = [sys.executable, "-B", str(Path(entrypoint.__file__).resolve()), *argv[1:]]
    assert received["executable"] == sys.executable
    assert received["command"] == subprocess.list2cmdline(command)
    assert received["desktop"].startswith("LabelmeScreenshot_")
    assert received["access"] & 0x0100 == 0
    assert received["desktop_from_startup"] == received["desktop"]
    assert ("lpDesktop", wintypes.LPWSTR) in received["startup_fields"]
    assert received["startup_size"] == ctypes.sizeof(apis["kernel32"].CreateProcessW.argtypes[-2]._type_)
    assert received["startup_flags"] == subprocess.STARTF_USESTDHANDLES
    assert received["flags"] == subprocess.CREATE_NO_WINDOW | 0x00000400
    assert received["inherit"] is True
    assert received["std_handles"][1] == received["std_handles"][2]
    for handle in set(received["std_handles"]):
        with pytest.raises(OSError):
            os.get_handle_inheritable(handle)
    assert received["env"]["LABELME_SCREENSHOT_DESKTOP"] == received["desktop"]
    assert received["env"]["QT_QPA_PLATFORM"] == "windows"
    assert not Path(received["env"]["HOME"]).exists()
    log = (tmp_path / "原生运行日志.txt").read_text(encoding="utf-8")
    assert {path.name for path in tmp_path.iterdir()} == {"原生运行日志.txt"}
    assert events[-1] == ("desktop-close", 101)
    if failure == "create_failed":
        assert "CreateProcessW" in log and "WinError 5" in log
        assert "退出码：未知" in log
        assert not any(event[0] in ("wait", "terminate", "handle-close") for event in events)
    else:
        if failure not in ("exit_failed", "terminate_failed"):
            assert f"退出码：{raw_exit} ({raw_exit:#x})" in log
        else:
            assert "退出码：未知" in log
        if failure in ("thread_close_failed", "process_close_failed"):
            assert "CloseHandle" in log
        if failure == "desktop_close_failed":
            assert "CloseDesktop" in log
        if failure == "exit_failed":
            assert "GetExitCodeProcess" in log or "WinError 5" in log
        if failure == "terminate_failed":
            assert "TerminateProcess" in log or "WinError 5" in log
        if failure == "wait_failed":
            assert "WaitForSingleObject" in log and "WinError 5" in log
        assert "模拟子进程输出" in log and "模拟程序日志" in log
        assert "模拟子进程输出" in capsys.readouterr().err
        assert events[:3] == [("create", 101), ("start", 301), ("wait", 45000)]
        assert events[-3:] == [("handle-close", 302), ("handle-close", 301), ("desktop-close", 101)]
        assert [event for event in events if event[0] == "terminate"] == ([("terminate", 301)] if failure in ("timeout", "interrupt", "terminate_failed", "wait_failed") else [])
        waits = [milliseconds for action, milliseconds in events if action == "wait"]
        assert all(0 <= milliseconds <= 45000 for milliseconds in waits)
        assert 0xFFFFFFFF not in waits
        if failure in ("timeout", "interrupt"):
            assert ("超时" if failure == "timeout" else "KeyboardInterrupt") in log


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 专用桌面检查")
@pytest.mark.parametrize("actual,expected", [
    ("Default", ""), ("Default", "LabelmeScreenshot_owned"),
    ("LabelmeScreenshot_other", "LabelmeScreenshot_owned"),
    ("LabelmeScreenshot_owned", "LabelmeScreenshot_owned"),
])
def test_native_desktop_requires_actual_owned_thread_desktop(monkeypatch, actual, expected):
    import ctypes
    from types import SimpleNamespace
    from labelme import __main__ as entrypoint

    def thread_id():
        return 11
    def thread_desktop(thread):
        assert thread == 11
        return 101
    def desktop_name(handle, index, buffer, length, needed):
        assert handle == 101 and index == 2
        buffer.value = actual
        return 1
    apis = {"kernel32": SimpleNamespace(GetCurrentThreadId=thread_id),
            "user32": SimpleNamespace(GetThreadDesktop=thread_desktop, GetUserObjectInformationW=desktop_name)}
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: apis[name])
    monkeypatch.setenv("LABELME_SCREENSHOT_DESKTOP", expected)
    if actual == expected:
        assert entrypoint.native_screenshot_desktop() == expected
    else:
        with pytest.raises(RuntimeError, match="拒绝采集") as error:
            entrypoint.native_screenshot_desktop()
        assert actual in str(error.value)
        assert expected in str(error.value)


@pytest.fixture
def native_capture_context(monkeypatch):
    import ctypes
    import struct
    from types import SimpleNamespace
    from labelme import __main__ as entrypoint

    state = {"fault": None, "rect_reads": 0, "pid_reads": 0, "cleanup": [], "capture": []}
    buffer = ctypes.create_string_buffer(bytes([0, 0, 0, 0, 0, 0, 255, 0]) * (100 * 80 // 2))
    def process_id(hwnd, target):
        state["pid_reads"] += 1
        target._obj.value = os.getpid() + (1 if state["fault"] == "pid" or state["fault"] == "changed_pid" and state["pid_reads"] > 1 else 0)
        return 1
    def window_rect(hwnd, target):
        state["rect_reads"] += 1
        values = (10, 10, 110, 90)
        if state["fault"] == "changed_rect" and state["rect_reads"] > 1:
            values = (10, 10, 111, 90)
        target._obj.left, target._obj.top, target._obj.right, target._obj.bottom = values
        return 1
    def client_rect(hwnd, target):
        target._obj.left, target._obj.top = 0, 0
        target._obj.right, target._obj.bottom = (100, 80) if state["fault"] == "client_only" else (90, 60)
        return 1
    def frame_rect(hwnd, attribute, target, size):
        target._obj.left, target._obj.top, target._obj.right, target._obj.bottom = (10, 10, 110, 90)
        return 0
    def monitor_info(monitor, target):
        struct.pack_into("<iiii", target, 20, 0, 0, 109 if state["fault"] == "outside" else 200, 200)
        return 1
    def bitmap(dc, info, usage, bits, section, offset):
        state["bitmap_header"] = struct.unpack_from("<IiiHH", info)
        if state["fault"] == "blank":
            ctypes.memset(buffer, 0, len(buffer))
        bits._obj.value = ctypes.addressof(buffer)
        return 202
    def capture(hwnd, dc, flags):
        state["capture"].append((hwnd, dc, flags))
        return 0 if state["fault"] == "capture_failed" else 1
    def dpi_context(context):
        return 99
    def create_dc(source):
        return 201
    def select_bitmap(dc, selected):
        return 203
    def delete_bitmap(value):
        state["cleanup"].append(("bitmap", value))
        return 1
    def delete_dc(value):
        state["cleanup"].append(("dc", value))
        return 1
    def flush():
        return 1
    def monitor(hwnd, flags):
        return 204
    apis = {"user32": SimpleNamespace(SetThreadDpiAwarenessContext=dpi_context, GetWindowThreadProcessId=process_id,
        GetWindowRect=window_rect, GetClientRect=client_rect, MonitorFromWindow=monitor,
        GetMonitorInfoW=monitor_info, PrintWindow=capture),
        "gdi32": SimpleNamespace(CreateCompatibleDC=create_dc, CreateDIBSection=bitmap, SelectObject=select_bitmap,
            DeleteObject=delete_bitmap, DeleteDC=delete_dc, GdiFlush=flush),
        "dwmapi": SimpleNamespace(DwmGetWindowAttribute=frame_rect)}
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: apis[name], raising=False)
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=SimpleNamespace(
        instance=lambda: SimpleNamespace(platformName=lambda: "offscreen" if state["fault"] == "platform" else "windows")),
        QMessageBox=type("MessageBox", (), {})))
    window = SimpleNamespace(winId=lambda: 501, ui_theme_manager=SimpleNamespace(current_theme="modern"))
    return entrypoint, window, state, apis


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 原生截图调用")
@pytest.mark.parametrize("name,metadata_name", [("主窗口.png", "原生截图.json"), ("清空前主窗口.png", "清空前主窗口.json")])
def test_native_capture_uses_complete_top_down_window_pixels_and_printwindow_flag2(tmp_path, native_capture_context, name, metadata_name):
    import ctypes
    entrypoint, window, state, apis = native_capture_context
    entrypoint.save_native_screenshot(window, tmp_path, name)
    assert {path.name for path in tmp_path.iterdir()} == {name, metadata_name}
    assert state["capture"] == [(501, 201, 2)]
    assert state["bitmap_header"] == (40, 100, -80, 1, 32)
    assert state["cleanup"] == [("bitmap", 202), ("dc", 201)]
    assert apis["user32"].PrintWindow.argtypes == [ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.UINT]
    with Image.open(tmp_path / name) as image:
        assert image.size == (100, 80)
        assert image.getpixel((0, 0)) == (0, 0, 0)
        assert image.getpixel((1, 0)) == (255, 0, 0)
    report = json.loads((tmp_path / metadata_name).read_text(encoding="utf-8"))
    assert report == {"backend": "PrintWindow", "flags": 2, "pid": os.getpid(), "desktop": "LabelmeScreenshot_owned",
        "window_rect": [10, 10, 110, 90], "frame_rect": [10, 10, 110, 90], "client_rect": [0, 0, 90, 60],
        "work_area": [0, 0, 200, 200], "image_size": [100, 80], "theme": "modern"}


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 原生截图拒绝检查")
@pytest.mark.parametrize("fault,reason", [("pid", "其他进程"), ("platform", "Windows Qt"),
    ("client_only", "完整系统窗框"), ("outside", "超出"), ("blank", "空白"),
    ("changed_rect", "发生变化"), ("changed_pid", "发生变化"), ("capture_failed", None)])
def test_native_capture_rejects_invalid_source_without_success_output(tmp_path, native_capture_context, fault, reason):
    entrypoint, window, state, apis = native_capture_context
    state["fault"] = fault
    with pytest.raises((RuntimeError, OSError), match=reason):
        entrypoint.save_native_screenshot(window, tmp_path)
    assert not (tmp_path / "主窗口.png").exists()
    assert not (tmp_path / "原生截图.json").exists()
    if fault == "outside":
        assert {path.name for path in tmp_path.iterdir()} == {"原生失败原图.png"}
        with Image.open(tmp_path / "原生失败原图.png") as image:
            assert image.size == (100, 80)
            assert image.getpixel((1, 0)) == (255, 0, 0)
    else:
        assert list(tmp_path.iterdir()) == []
    if state["capture"]:
        assert state["cleanup"] == [("bitmap", 202), ("dc", 201)]


@pytest.mark.parametrize("name,clear_group", [("主窗口.png", False), ("原生截图.json", False), ("清空前主窗口.json", True)])
def test_native_screenshot_output_rejects_existing_files_before_window_creation(monkeypatch, tmp_path, name, clear_group):
    from labelme import __main__ as entrypoint

    sample = tmp_path / "sample.png"
    Image.new("RGB", (24, 16)).save(sample)
    sample.with_suffix(".json").write_text(json.dumps({"imagePath": sample.name, "shapes": []}), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    existing = output / name
    existing.write_bytes(b"original")
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    from types import SimpleNamespace
    def reject_application(arguments):
        pytest.fail("已有输出未在创建窗口前拒绝")
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=reject_application))
    with pytest.raises(FileExistsError):
        entrypoint.render_screenshots(str(sample), str(output), clear_group, native=True)
    assert existing.read_bytes() == b"original"
    assert {path.name for path in output.iterdir()} == {name}


def test_native_capture_source_has_no_window_adjustment_or_widget_render():
    import ast
    import inspect
    from labelme import __main__ as entrypoint

    tree = ast.parse(inspect.getsource(entrypoint.save_native_screenshot))
    calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "PrintWindow" in calls
    assert not {"render", "move", "resize", "setGeometry", "SetWindowPos", "SwitchDesktop"}.intersection(calls)
    renderer = ast.parse(inspect.getsource(entrypoint.render_screenshots))
    capture = next(node for node in ast.walk(renderer) if isinstance(node, ast.FunctionDef) and node.name == "capture")
    native = next(node for node in capture.body if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "native")
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"render", "move", "resize", "setGeometry"}
        for statement in native.body for node in ast.walk(statement))
    assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "save_native_screenshot" for node in ast.walk(native))



def test_native_desktop_rejects_non_windows_platform(monkeypatch):
    from labelme import __main__ as entrypoint

    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="仅支持 Windows"):
        entrypoint.native_screenshot_desktop()



def test_native_render_rejects_unowned_desktop_before_creating_window(monkeypatch, tmp_path):
    from labelme import __main__ as entrypoint

    created = []
    def reject_desktop():
        raise RuntimeError("非本次专用桌面")
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", reject_desktop)
    monkeypatch.setattr(entrypoint, "MainWindow", lambda *args, **kwargs: created.append(True))
    with pytest.raises(RuntimeError, match="专用桌面"):
        entrypoint.render_screenshots("sample.png", str(tmp_path), native=True)
    assert created == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 原生运行日志")
def test_native_launcher_preserves_existing_diagnostic_log_without_starting_process(monkeypatch, tmp_path):
    import ctypes
    from labelme import __main__ as entrypoint

    diagnostic = tmp_path / "原生运行日志.txt"
    diagnostic.write_text("已有诊断", encoding="utf-8")
    api_calls = []
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api_calls.append(args))
    monkeypatch.setattr(sys, "argv", ["labelme", "sample.jpg", f"--screenshot-output={tmp_path}", "--screenshot-native"])
    with pytest.raises(FileExistsError):
        entrypoint.launch_native_screenshot()
    assert diagnostic.read_text(encoding="utf-8") == "已有诊断"
    assert api_calls == []



def test_native_startup_settings_and_close_use_same_explicit_ini(qapp, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme import __main__ as entrypoint
    from labelme.dlcv import dlcv_tr
    from labelme.dlcv.store import STORE

    materials = tmp_path / "materials"
    materials.mkdir()
    sample = materials / "sample.png"
    Image.new("RGB", (24, 16)).save(sample)
    sample.with_suffix(".json").write_text(json.dumps({"imagePath": sample.name, "imageWidth": 24,
        "imageHeight": 16, "flags": {}, "shapes": [{"label": "外部标注", "shape_type": "polygon",
        "points": [[1, 1], [12, 1], [12, 10], [1, 10]], "flags": {}}]}), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    state = {}
    base_window = entrypoint.MainWindow
    try:
        previous_window = STORE.main_window
    except AssertionError:
        previous_window = None
    previous_translator = STORE.q_translator
    monkeypatch.setattr(dlcv_tr, "lang", None)
    monkeypatch.setenv("WINDIR", str(tmp_path))
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, os.environ.get(name, str(tmp_path)))
    class ExistingApplication:
        def __new__(cls, arguments):
            return qapp
        @staticmethod
        def instance():
            return qapp
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=ExistingApplication))
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")

    class ObservedWindow(base_window):
        def __init__(self, *args, **kwargs):
            state["root"] = Path(os.environ["HOME"]).resolve()
            state["settings"], state["dev_settings"] = self.settings, self.dev_setting
            for settings, name in ((self.settings, "labelme.ini"), (self.dev_setting, "dev.ini")):
                assert settings.format() == QtCore.QSettings.IniFormat
                assert Path(settings.fileName()).resolve() == state["root"] / name
            assert self.settings.value("window/position") == QtCore.QPoint(32, 32)
            assert self.settings.value("ui/theme") == "modern"
            assert not self.settings.contains("window/size")
            disk = QtCore.QSettings(self.settings.fileName(), QtCore.QSettings.IniFormat)
            assert disk.value("window/position") == QtCore.QPoint(32, 32)
            state["before_constructor"] = True
            super().__init__(*args, **kwargs)
            assert self.settings is state["settings"]
            assert self.dev_setting is state["dev_settings"]
            self.settings.setValue("capture/save-marker", "同一设置文件")
            self.dev_setting.setValue("capture/save-marker", "同一开发设置文件")

        def closeEvent(self, event):
            state["close_settings"] = self.settings
            state["close_dev_settings"] = self.dev_setting
            state["configuration_alive_at_close"] = state["root"].is_dir()
            super().closeEvent(event)
            self.settings.sync()
            self.dev_setting.sync()
            disk = QtCore.QSettings(self.settings.fileName(), QtCore.QSettings.IniFormat)
            developer = QtCore.QSettings(self.dev_setting.fileName(), QtCore.QSettings.IniFormat)
            state.update(close_status=self.settings.status(), developer_close_status=self.dev_setting.status(),
                saved_marker=disk.value("capture/save-marker"), saved_position=disk.value("window/position"),
                expected_position=self.pos(), saved_filename=disk.value("filename"), expected_filename=self.filename,
                saved_size=disk.contains("window/size"), developer_marker=developer.value("capture/save-marker"))

    monkeypatch.setattr(entrypoint, "MainWindow", ObservedWindow)
    def check_settings(window, directory, name):
        assert state["before_constructor"]
        assert window.settings is state["settings"]
        assert window.dev_setting is state["dev_settings"]
        assert [shape.label for shape in window.canvas.shapes] == ["外部标注"]
        assert name == "主窗口.png"
        assert Path(directory) == output
        state["captured"] = True
    monkeypatch.setattr(entrypoint, "save_native_screenshot", check_settings)
    try:
        entrypoint.render_screenshots(str(sample), str(output), native=True)
        assert state["captured"]
        assert state["configuration_alive_at_close"], "正式关闭保存前，截图临时配置目录已被清理"
        assert state["close_settings"] is state["settings"]
        assert state["close_dev_settings"] is state["dev_settings"]
        assert state["close_status"] == state["developer_close_status"] == QtCore.QSettings.NoError
        assert state["saved_marker"] == "同一设置文件"
        assert state["developer_marker"] == "同一开发设置文件"
        assert state["saved_position"] == state["expected_position"]
        assert state["saved_filename"] == state["expected_filename"]
        assert state["saved_size"]
        assert not state["root"].exists()
    finally:
        STORE.register_main_window(previous_window)
        STORE.q_translator = previous_translator



def test_native_startup_ini_sync_failure_stops_before_application_or_window(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from qtpy import QtCore
    from labelme import __main__ as entrypoint

    materials = tmp_path / "materials"
    materials.mkdir()
    sample = materials / "sample.png"
    Image.new("RGB", (24, 16)).save(sample)
    sample.with_suffix(".json").write_text(json.dumps({"imagePath": sample.name, "shapes": []}), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    created = []
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    monkeypatch.setattr(QtCore.QSettings, "status", lambda self: QtCore.QSettings.AccessError)
    class RejectedWindow:
        def __init__(self, *args, **kwargs):
            created.append("window")
    monkeypatch.setattr(entrypoint, "MainWindow", RejectedWindow)
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=lambda *args: created.append("application")))
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, os.environ.get(name, str(tmp_path)))
    with pytest.raises(RuntimeError, match="隔离 INI 启动配置写入失败"):
        entrypoint.render_screenshots(str(sample), str(output), native=True)
    assert created == []
    assert not (output / "主窗口.png").exists()
    report = json.loads((output / "场景结果.json").read_text(encoding="utf-8"))
    assert report["success"] is False
    assert "隔离 INI 启动配置写入失败" in report["failure"]



@pytest.mark.parametrize("case,field,path_kind", [
    ("readonly-save", "imagePath", "absolute"), ("readonly-save", "imagePath", "relative"),
    ("readonly-save", "image_path_list", "absolute"), ("readonly-save", "image_path_list", "relative"),
    ("readonly-save", "img_name_list", "absolute"), ("readonly-save", "img_name_list", "relative"),
    ("readonly-save", "image_path_list", "same_directory"),
    ("save", "image_path_list", "absolute"), ("autosave", "img_name_list", "relative"),
    ("clear", "imagePath", "absolute"),
])
def test_writable_capture_rejects_unsafe_targets_or_copies_all_into_owned_scope(monkeypatch, tmp_path, case, field, path_kind):
    from types import SimpleNamespace
    from labelme import __main__ as entrypoint

    materials = tmp_path / "materials"
    outside = tmp_path / "outside"
    materials.mkdir()
    outside.mkdir()
    source = materials / "sample.jpg"
    member = (materials if path_kind == "same_directory" else outside) / "member.jpg"
    for image, color in ((source, (20, 80, 160)), (member, (160, 80, 20))):
        Image.new("RGB", (24, 16), color).save(image)
    reference = str(source if field == "imagePath" else member) if path_kind == "absolute" else "../outside/member.jpg" if path_kind == "relative" else member.name
    data = {"imagePath": source.name, "imageWidth": 24, "imageHeight": 16, "flags": {},
        "shapes": [{"label": "标注", "shape_type": "polygon", "points": [[1, 1], [12, 1], [12, 10], [1, 10]]}]}
    data[field] = reference if field == "imagePath" else [source.name, reference]
    source.with_suffix(".json").write_text(json.dumps(data), encoding="utf-8")
    member.with_suffix(".json").write_text(json.dumps({**data, "imagePath": member.name,
        "image_path_list": [member.name], "img_name_list": [member.name]}), encoding="utf-8")
    originals = {path: path.read_bytes() for directory in (materials, outside) for path in directory.iterdir()}
    image_bytes = {path.name: content for path, content in originals.items() if path.suffix == ".jpg"}
    output = tmp_path / "output"
    output.mkdir()
    state = {"copies": [], "applications": 0}

    class ScopeChecked(RuntimeError):
        pass

    original_copy = shutil.copy2
    def record_copy(source_path, target, *args, **kwargs):
        state["copies"].append(Path(target))
        assert Path(target).resolve().is_relative_to((output / "材料副本").resolve())
        return original_copy(source_path, target, *args, **kwargs)
    def inspect_before_application(arguments):
        state["applications"] += 1
        root = (output / "材料副本").resolve()
        copied_images = list(root.rglob(source.name))
        assert len(copied_images) == 1
        copied_json = copied_images[0].with_suffix(".json")
        copied_data = json.loads(copied_json.read_text(encoding="utf-8"))
        primary = (copied_json.parent / copied_data["imagePath"]).resolve()
        targets = [primary]
        targets.extend((copied_json.parent / name).resolve() for name in copied_data.get("image_path_list", []))
        targets.extend((primary.parent / name).resolve() for name in copied_data.get("img_name_list", []))
        for target in targets:
            assert target.is_relative_to(root)
            assert target.is_file()
            assert target.read_bytes() == image_bytes[target.name]
        state["scope_checked"] = True
        raise ScopeChecked
    monkeypatch.setattr(shutil, "copy2", record_copy)
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=inspect_before_application))
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, os.environ.get(name, str(tmp_path)))
    try:
        entrypoint.render_screenshots(str(source), str(output), case=case, native=True)
    except ScopeChecked:
        assert state["scope_checked"]
    except ValueError:
        assert state["applications"] == 0
        assert state["copies"] == []
    else:
        pytest.fail("捕获入口未完成复制范围检查")
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert not (output / "主窗口.png").exists()
    assert not (output / "原生截图.json").exists()



def test_prepare_capture_materials_copies_cross_directory_group_and_rebases_absolute_references(tmp_path):
    from labelme import __main__ as entrypoint

    source_root = tmp_path / "source"
    first = source_root / "images" / "camera1" / "first.png"
    second = source_root / "images" / "camera2" / "second.png"
    annotation = source_root / "labels" / "review.json"
    for directory in (first.parent, second.parent, annotation.parent):
        directory.mkdir(parents=True)
    for image in (first, second):
        Image.new("RGB", (24, 16), (20, 80, 160)).save(image)
    data = {"imagePath": str(first), "imageWidth": 24, "imageHeight": 16, "flags": {},
        "shapes": [{"label": "跨目录", "shape_type": "polygon", "points": [[1, 1], [12, 1], [12, 10], [1, 10]]}],
        "image_path_list": [str(first), str(second)], "img_name_list": [first.name, "../camera2/second.png"]}
    annotation.write_text(json.dumps(data), encoding="utf-8")
    originals = {path: path.read_bytes() for path in source_root.rglob("*") if path.is_file()}
    clone_root = tmp_path / "clone"
    copied = entrypoint.prepare_screenshot_materials(annotation, source_root, clone_root, writable=True)
    assert copied == clone_root / "labels" / "review.json"
    copied_data = json.loads(copied.read_text(encoding="utf-8"))
    copied_images = [clone_root / image.relative_to(source_root) for image in (first, second)]
    assert (copied.parent / copied_data["imagePath"]).resolve() == copied_images[0]
    assert [(copied.parent / name).resolve() for name in copied_data["image_path_list"]] == copied_images
    assert [(copied_images[0].parent / name).resolve() for name in copied_data["img_name_list"]] == copied_images
    assert copied_data["shapes"] == data["shapes"]
    for original, target in zip((first, second), copied_images):
        assert target.read_bytes() == originals[original]
    assert entrypoint.verify_screenshot_targets(copied_images[0], copied, {
        key: copied_data[key] for key in ("image_path_list", "img_name_list")}, clone_root) == copied_images
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("target", ["primary", "sidecar", "image_path_list", "img_name_list"])
def test_capture_target_validation_rejects_every_external_write_target(tmp_path, target):
    from labelme import __main__ as entrypoint

    owned = tmp_path / "owned"
    owned.mkdir()
    image = owned / "sample.png"
    external = tmp_path / "outside.png"
    for path in (image, external):
        Image.new("RGB", (24, 16)).save(path)
    sidecar = owned / "sample.json"
    sidecar.write_text(json.dumps({"imagePath": image.name, "shapes": []}), encoding="utf-8")
    originals = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    primary = external if target == "primary" else image
    json_target = tmp_path / "outside.json" if target == "sidecar" else sidecar
    other_data = {target: [str(external)]} if target in ("image_path_list", "img_name_list") else {}
    with pytest.raises(ValueError, match="副本之外"):
        entrypoint.verify_screenshot_targets(primary, json_target, other_data, owned)
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert {path for path in tmp_path.rglob("*") if path.is_file()} == set(originals)



def test_capture_cli_forwards_declared_case_root_output_and_filter(monkeypatch, tmp_path):
    from labelme import __main__ as entrypoint

    calls = []
    root = tmp_path / "materials"
    monkeypatch.setattr(sys, "argv", ["labelme", "labels/custom.json", f"--screenshot-output={tmp_path}",
        "--screenshot-native", "--screenshot-case", "autosave", "--screenshot-data-root", str(root),
        "--output", "labels/final.json", "--screenshot-filter", "annotated"])
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(entrypoint, "render_screenshots", lambda *args, **kwargs: calls.append((args, kwargs)))
    entrypoint.main()
    assert calls == [(("labels/custom.json", tmp_path, False), {"readonly_save": False, "native": True,
        "case": "autosave", "data_root": root, "output": "labels/final.json", "filter_mode": "annotated", "manifest_path": None})]



def capture_annotation(image_path, label="外部"):
    return {"imagePath": image_path.name, "imageWidth": 96, "imageHeight": 64, "flags": {},
        "shapes": [] if label is None else [{"label": label, "shape_type": "polygon",
            "points": [[8, 8], [40, 8], [40, 32], [8, 32]], "flags": {}}]}



def run_formal_capture(tmp_path, source, *, case="open", root=None, output=None, filter_mode="all"):
    repository = Path(__file__).resolve().parents[3]
    destination = tmp_path / "capture"
    destination.mkdir()
    command = [sys.executable, "-B", str(repository / "labelme/__main__.py"), str(source),
        "--screenshot-output", str(destination), "--screenshot-native", "--screenshot-case", case, "--screenshot-filter", filter_mode]
    if root is not None:
        command += ["--screenshot-data-root", str(root)]
    if output is not None:
        command += ["--output", str(output)]
    result = subprocess.run(command, cwd=repository, env=os.environ.copy(), capture_output=True,
        text=True, encoding="utf-8", timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((destination / "场景结果.json").read_text(encoding="utf-8"))
    assert report["case"] == case and report["success"] is True
    assert Path(report["material_root"]) == destination / "材料副本"
    metadata = json.loads((destination / "原生截图.json").read_text(encoding="utf-8"))
    assert metadata["backend"] == "PrintWindow" and metadata["flags"] == 2
    left, top, right, bottom = metadata["frame_rect"]
    work_left, work_top, work_right, work_bottom = metadata["work_area"]
    assert work_left <= left < right <= work_right and work_top <= top < bottom <= work_bottom
    with Image.open(destination / "主窗口.png") as screenshot:
        assert list(screenshot.size) == metadata["image_size"]
        assert screenshot.size[0] > metadata["client_rect"][2]
        assert screenshot.size[1] > metadata["client_rect"][3]
    return destination, report


@pytest.mark.parametrize("state", ["empty", "missing", "broken", "custom_output"])
def test_formal_capture_reads_external_state_and_selected_custom_json(tmp_path, state):
    from dlcv_core.image_json import write_image_json

    root = tmp_path / "materials"
    root.mkdir()
    image = root / "sample.png"
    Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
    write_image_json(image, capture_annotation(image, "旧内嵌"))
    annotation = image.with_suffix(".json")
    source, requested = image, None
    if state == "empty":
        annotation.write_text(json.dumps(capture_annotation(image, None)), encoding="utf-8")
    elif state == "broken":
        annotation.write_text("{", encoding="utf-8")
    elif state == "custom_output":
        annotation = root / "labels" / "custom.json"
        annotation.parent.mkdir()
        annotation.write_text(json.dumps({**capture_annotation(image), "imagePath": "../sample.png"}), encoding="utf-8")
        source, requested = annotation, "labels/other-output"
    originals = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    destination, report = run_formal_capture(tmp_path, source, case="invalid-json" if state == "broken" else "open", root=root, output=requested)
    assert report["labels"] == (["外部"] if state == "custom_output" else [])
    if state == "broken":
        assert report["errors"]
        assert (destination / "错误提示.png").is_file()
    else:
        assert report["loaded"] and report["errors"] == []
        assert Path(report["displayed_image"]).resolve() == destination / "材料副本" / image.name
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("case", ["save", "autosave", "clear", "reopen"])
def test_formal_capture_custom_json_save_auto_clear_and_reopen(tmp_path, case):
    from dlcv_core.image_json import read_image_json, write_image_json

    root = tmp_path / "materials"
    image = root / "images" / "sample.png"
    annotation = root / "labels" / "review.json"
    image.parent.mkdir(parents=True)
    annotation.parent.mkdir()
    Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
    write_image_json(image, capture_annotation(image, "旧内嵌"))
    annotation.write_text(json.dumps({**capture_annotation(image, "原始"), "imagePath": "../images/sample.png"}), encoding="utf-8")
    originals = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    requested = "labels/saved-as.json" if case == "save" else None
    destination, report = run_formal_capture(tmp_path, annotation, case=case, root=root, output=requested)
    clone = destination / "材料副本"
    if case in ("save", "autosave"):
        expected_json = clone / "labels" / ("saved-as.json" if case == "save" else "review.json")
        assert Path(report["saved_json"]) == expected_json
        assert report["save_returned"] and report["reopened"]
        assert report["labels"] == ["保存验证"]
        external = json.loads(expected_json.read_text(encoding="utf-8"))
        assert external["shapes"][0]["label"] == "保存验证"
        assert read_image_json(clone / "images/sample.png")["shapes"] == external["shapes"]
        assert not (clone / "images/sample.json").exists()
    elif case == "clear":
        assert report["labels"] == []
        assert not (clone / "labels/review.json").exists()
        assert read_image_json(clone / "images/sample.png") is None
    else:
        assert report["reopened"] and report["labels"] == ["原始"]
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("filter_mode,expected", [
    ("annotated", {"a_labeled.png", "b_empty.png"}), ("unannotated", {"c_unlabeled.png"}),
    ("all", {"a_labeled.png", "b_empty.png", "c_unlabeled.png"}),
])
def test_formal_directory_capture_statistics_and_filter_use_external_json(tmp_path, filter_mode, expected):
    from dlcv_core.image_json import write_image_json

    root = tmp_path / "materials"
    root.mkdir()
    for name, label in (("a_labeled.png", "外部"), ("b_empty.png", None), ("c_unlabeled.png", None)):
        image = root / name
        Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
        write_image_json(image, capture_annotation(image, "旧内嵌"))
        if name != "c_unlabeled.png":
            image.with_suffix(".json").write_text(json.dumps(capture_annotation(image, label)), encoding="utf-8")
    originals = {path: path.read_bytes() for path in root.iterdir()}
    destination, report = run_formal_capture(tmp_path, root, case="directory", root=root, filter_mode=filter_mode)
    assert {Path(path).name for path in report["visible_images"]} == expected
    assert "外部: 1" in report["statistics"] and "总数: 1" in report["statistics"]
    assert "旧内嵌" not in report["statistics"]
    assert all(path.read_bytes() == content for path, content in originals.items())



def test_formal_capture_group_save_updates_both_cross_directory_images(tmp_path):
    from dlcv_core.image_json import read_image_json, write_image_json

    root = tmp_path / "materials"
    first = root / "images/camera1/first.png"
    second = root / "images/camera2/second.png"
    annotation = root / "labels/review.json"
    for directory in (first.parent, second.parent, annotation.parent):
        directory.mkdir(parents=True)
    for image in (first, second):
        Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
        write_image_json(image, capture_annotation(image, "旧内嵌"))
    data = {**capture_annotation(first, "原始"), "imagePath": "../images/camera1/first.png",
        "image_path_list": ["../images/camera1/first.png", "../images/camera2/second.png"],
        "img_name_list": [first.name, "../camera2/second.png"]}
    annotation.write_text(json.dumps(data), encoding="utf-8")
    originals = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    destination, report = run_formal_capture(tmp_path, annotation, case="save", root=root)
    clone = destination / "材料副本"
    external = json.loads((clone / "labels/review.json").read_text(encoding="utf-8"))
    assert external["shapes"][0]["label"] == "保存验证"
    assert report["save_returned"] and report["reopened"]
    for original in (first, second):
        image = clone / original.relative_to(root)
        embedded = read_image_json(image)
        assert embedded["shapes"] == external["shapes"]
        for key in ("image_path_list", "img_name_list"):
            assert [(image.parent / name).resolve() for name in embedded[key]] == [clone / first.relative_to(root), clone / second.relative_to(root)]
        assert (embedded["imageWidth"], embedded["imageHeight"]) == (96, 64)
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("absolute", [False, True])
def test_output_mapping_stays_inside_copy_before_application_creation(monkeypatch, tmp_path, absolute):
    from types import SimpleNamespace
    from labelme import __main__ as entrypoint

    source_root = tmp_path / "materials"
    source_root.mkdir()
    image = source_root / "sample.png"
    Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
    image.with_suffix(".json").write_text(json.dumps(capture_annotation(image)), encoding="utf-8")
    output = tmp_path / "capture"
    output.mkdir()
    originals = {path: path.read_bytes() for path in source_root.iterdir()}
    requested = source_root / "labels/output" if absolute else "labels/output"
    class MappingChecked(Exception):
        pass
    def inspect_before_application(arguments):
        assert (output / "材料副本/labels/output").is_dir()
        assert not (source_root / "labels").exists()
        raise MappingChecked
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=inspect_before_application))
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(key, os.environ.get(key, str(tmp_path)))
    with pytest.raises(MappingChecked):
        entrypoint.render_screenshots(str(image), str(output), native=True, case="save", data_root=source_root, output=str(requested))
    report = json.loads((output / "场景结果.json").read_text(encoding="utf-8"))
    assert Path(report["requested_output"]) == output / "材料副本/labels/output"
    assert report["success"] is False
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("requested", ["../outside/result.json", "absolute"])
def test_output_outside_material_root_is_rejected_before_application(monkeypatch, tmp_path, requested):
    from types import SimpleNamespace
    from labelme import __main__ as entrypoint

    source_root = tmp_path / "materials"
    source_root.mkdir()
    image = source_root / "sample.png"
    Image.new("RGB", (96, 64)).save(image)
    output = tmp_path / "capture"
    output.mkdir()
    outside = tmp_path / "outside/result.json"
    calls = []
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=lambda *args: calls.append(args)))
    with pytest.raises(ValueError, match="--output"):
        entrypoint.render_screenshots(str(image), str(output), native=True, case="save", data_root=source_root,
            output=str(outside) if requested == "absolute" else requested)
    assert calls == [] and not outside.exists()
    assert not (output / "主窗口.png").exists()


def test_formal_native_readonly_save_preserves_edits_and_captures_actual_error(tmp_path):
    from dlcv_core.image_json import read_image_json

    root = tmp_path / "materials"
    root.mkdir()
    image = root / "sample.png"
    Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
    image.with_suffix(".json").write_text(json.dumps(capture_annotation(image, "原始")), encoding="utf-8")
    originals = {path: path.read_bytes() for path in root.iterdir()}
    destination, report = run_formal_capture(tmp_path, image, case="readonly-save", root=root)
    assert report["save_returned"] is False and report["dirty"] is True
    assert report["edited_label"] == "未保存验证" and report["image_unchanged"] is True
    assert report["embedded_annotation"] is None
    assert read_image_json(destination / "材料副本/sample.png") is None
    external = json.loads((destination / "材料副本/sample.json").read_text(encoding="utf-8"))
    assert external["shapes"][0]["label"] == "未保存验证"
    assert report["errors"] and "Permission denied" in report["errors"][0]["message"]
    assert (destination / "错误提示.png").is_file()
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.fixture
def screenshot_manifest():
    path = os.environ.get("LABELME_SCREENSHOT_TEST_MANIFEST")
    if not path:
        pytest.skip("固定场景需要 C 的独立材料，使用 LABELME_SCREENSHOT_TEST_MANIFEST 指定 cases.json")
    manifest = Path(path).resolve(strict=True)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    return manifest, data


def test_manifest_cli_forwards_single_manifest_without_filename(monkeypatch, tmp_path):
    from labelme import __main__ as entrypoint

    manifest = tmp_path / "cases.json"
    calls = []
    monkeypatch.setattr(sys, "argv", ["labelme", "--screenshot-native", f"--screenshot-output={tmp_path}",
        "--screenshot-manifest", str(manifest), "--screenshot-case", "L06-valid-empty"])
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(entrypoint, "render_screenshots", lambda *args, **kwargs: calls.append((args, kwargs)))
    entrypoint.main()
    assert calls == [((None, tmp_path, False), {"readonly_save": False, "native": True,
        "case": "L06-valid-empty", "data_root": None, "output": None, "filter_mode": "all", "manifest_path": manifest})]


@pytest.mark.parametrize("fault", ["unknown_id", "missing_manifest", "duplicate_id", "schema", "arbitrary_action"])
def test_manifest_rejects_unknown_or_nonfixed_inputs_before_copy_or_window(monkeypatch, tmp_path, screenshot_manifest, fault):
    from labelme import __main__ as entrypoint

    original, data = screenshot_manifest
    case_id = "L02-manual-nonstem"
    if fault == "unknown_id":
        monkeypatch.setattr(sys, "argv", ["labelme", "--screenshot-native", "--screenshot-output", str(tmp_path),
            "--screenshot-manifest", str(original), "--screenshot-case", "unknown-case"])
        with pytest.raises(SystemExit) as error:
            entrypoint.main()
        assert error.value.code == 2
        return
    case = next(item for item in data["cases"] if item["id"] == case_id)
    if fault == "duplicate_id":
        data["cases"].append(case)
    elif fault == "schema":
        data["schema_version"] = 2
    elif fault == "arbitrary_action":
        case["steps"][1]["action"] = "execute_command"
    manifest = tmp_path / "cases.json"
    manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    copies, windows = [], []
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    monkeypatch.setattr(entrypoint, "prepare_screenshot_materials", lambda *args, **kwargs: copies.append(args))
    monkeypatch.setattr(entrypoint, "MainWindow", lambda *args, **kwargs: windows.append(args))
    with pytest.raises(ValueError):
        entrypoint.render_screenshots(None, str(tmp_path), native=True, case=case_id,
            manifest_path=None if fault == "missing_manifest" else manifest)
    assert copies == windows == []
    assert not (tmp_path / "材料副本").exists()


def manifest_annotation_differences(actual, expected, base, location):
    """路径按对应存储目录比较，文本标记保留完整 true/false 集合。"""
    differences = []
    for field, value in expected.items():
        if field not in actual:
            differences.append(f"{location} 缺少 {field}")
            continue
        observed = actual[field]
        if field == "imagePath":
            equal = (base / observed).resolve() == (base / value).resolve()
        elif field in ("image_path_list", "img_name_list"):
            member_base = base if field == "image_path_list" else (base / expected["imagePath"]).resolve().parent
            equal = [(member_base / name).resolve() for name in observed] == [(member_base / name).resolve() for name in value]
        elif field == "shapes":
            equal = len(observed) == len(value)
            for index, shape in enumerate(value):
                if index >= len(observed):
                    break
                differences.extend(manifest_annotation_differences(observed[index], shape, base, f"{location} shape {index}"))
        else:
            equal = observed == value
        if not equal:
            differences.append(f"{location} {field}：实际 {observed!r}，预期 {value!r}")
    return differences


@pytest.mark.parametrize("case_id,stage_names", [
    ("L01-explicit-json", ["初始主窗口", "导入目录后主窗口", "已标注筛选主窗口", "未标注筛选主窗口", "目录统计主窗口", "目录文本标记统计主窗口", "目录标签统计主窗口", "目录总数主窗口"]),
    ("L01-image-outputdir", ["初始主窗口", "导入目录后主窗口", "目录统计主窗口", "目录文本标记统计主窗口", "目录标签统计主窗口", "目录总数主窗口"]),
    ("L02-manual-nonstem", ["初始主窗口", "手动保存后主窗口", "重开主窗口"]),
    ("L03-automatic-nonstem", ["初始主窗口", "自动第一次主窗口", "自动第二次主窗口", "重开主窗口"]),
    ("L04-crossdir-manual", ["初始主窗口", "另存后主窗口", "连续保存后主窗口", "重开主窗口", "清空后主窗口", "主图重开窗口"]),
    ("L05-crossdir-automatic", ["初始主窗口", "另存后主窗口", "自动第一次主窗口", "自动第二次主窗口", "重开主窗口", "清空后主窗口", "主图重开窗口"]),
    ("L06-valid-empty", ["初始主窗口", "合法空标注主窗口"]),
])
def test_manifest_fixed_flow_matches_independent_materials(tmp_path, screenshot_manifest, case_id, stage_names):
    from dlcv_core.image_json import read_image_json

    manifest, data = screenshot_manifest
    case = next(item for item in data["cases"] if item["id"] == case_id)
    root = Path(case["fixture_root"]).resolve(strict=True)
    originals = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    destination = tmp_path / "capture"
    destination.mkdir()
    repository = Path(__file__).resolve().parents[3]
    command = [sys.executable, "-B", str(repository / "labelme/__main__.py"), "--screenshot-output", str(destination),
        "--screenshot-native", "--screenshot-manifest", str(manifest), "--screenshot-case", case_id]
    process = subprocess.run(command, cwd=repository, env=os.environ.copy(), capture_output=True,
        text=True, encoding="utf-8", timeout=90)
    assert process.returncode == 0, process.stdout + process.stderr
    assert all((root / relative).read_bytes() == content for relative, content in originals.items())
    report = json.loads((destination / "场景结果.json").read_text(encoding="utf-8"))
    assert report["success"] is True and report["case"] == case_id
    assert report["errors"] == report["dialog_capture_errors"] == []
    clone = destination / "材料副本"
    assert Path(report["material_root"]) == clone
    assert Path(report["manifest"]) == manifest
    stages = report["stages"]
    assert [stage["name"] for stage in stages] == stage_names
    initial_root = Path(stages[0]["material_root"])
    assert {path.relative_to(initial_root) for path in initial_root.rglob("*") if path.is_file()} == set(originals)
    assert all((initial_root / relative).read_bytes() == content for relative, content in originals.items())
    differences = []
    for stage in stages:
        stage_root = Path(stage["material_root"])
        assert stage_root.is_relative_to(destination / "阶段材料")
        if stage["active_json"]:
            assert Path(stage["active_json"]).is_relative_to(stage_root)
            assert Path(stage["working_json"]).is_relative_to(clone)
        if case_id.startswith("L01") and stage["name"] != "初始主窗口":
            assert stage["displayed_image"] is None
        else:
            assert Path(stage["displayed_image"]).is_relative_to(clone)
        for relative in (name for name in originals if name.suffix.lower() == ".png"):
            with Image.open(root / relative) as original, Image.open(stage_root / relative) as actual:
                assert (actual.mode, actual.size, actual.tobytes()) == (original.mode, original.size, original.tobytes())
        screenshot = Path(stage["screenshot"])
        metadata = json.loads(screenshot.with_suffix(".json").read_text(encoding="utf-8"))
        assert metadata["backend"] == "PrintWindow" and metadata["flags"] == 2
        assert metadata["desktop"].startswith("LabelmeScreenshot_")
        left, top, right, bottom = metadata["frame_rect"]
        wl, wt, wr, wb = metadata["work_area"]
        assert wl <= left < right <= wr and wt <= top < bottom <= wb
        with Image.open(screenshot) as image:
            assert list(image.size) == metadata["image_size"]
            assert image.width > metadata["client_rect"][2] and image.height > metadata["client_rect"][3]
    if case_id.startswith("L01"):
        assert (destination / "目录导入确认.png").is_file()
        dialog_metadata = json.loads((destination / "目录导入确认.json").read_text(encoding="utf-8"))
        assert dialog_metadata["backend"] == "PrintWindow" and dialog_metadata["flags"] == 2
        assert dialog_metadata["pid"] == metadata["pid"] and dialog_metadata["desktop"] == metadata["desktop"]
    expected = case["expected"]
    initial = expected.get("initial", expected)
    initial_shapes = initial.get("canvas_shapes", initial.get("initial_canvas_shapes", initial.get("previous_canvas_shapes")))
    if initial_shapes is not None:
        shapes = [{**shape, **shape.get("other_data", {})} for shape in stages[0]["canvas_shapes"]]
        differences.extend(manifest_annotation_differences({"shapes": shapes}, {"shapes": initial_shapes}, initial_root, "初始画布"))
    initial_flags = initial.get("flags", initial.get("initial_flags"))
    if case_id == "L06-valid-empty":
        initial_flags = None
    if initial_flags is not None and stages[0]["flags"] != initial_flags:
        differences.append(f"初始 flags：{stages[0]['flags']!r}，预期 {initial_flags!r}")
    if case_id.startswith("L01"):
        assert Path(stages[0]["active_json"]) == initial_root / expected["active_json"]
        for category in ("shape_counts", "flag_counts"):
            for label, count in expected["directory_count"][category].items():
                assert f"{label}: {count}" in report["statistics"]
        assert f"共扫描 {len(expected['directory_count']['json_sources'])} 份标注" in report["statistics"]
        assert f"总数: {sum(expected['directory_count']['shape_counts'].values()) + sum(expected['directory_count']['flag_counts'].values())}" in report["statistics"]
    snapshot_names = {
        "L02-manual-nonstem": ["手动保存后主窗口"],
        "L03-automatic-nonstem": ["自动第一次主窗口", "自动第二次主窗口"],
        "L04-crossdir-manual": ["另存后主窗口", "连续保存后主窗口"],
        "L05-crossdir-automatic": ["另存后主窗口", "自动第一次主窗口", "自动第二次主窗口"],
    }.get(case_id, [])
    for name, snapshot in zip(snapshot_names, expected.get("snapshots", []), strict=True):
        stage = next(item for item in stages if item["name"] == name)
        stage_root = Path(stage["material_root"])
        target = stage_root / snapshot["json_path"]
        assert Path(stage["active_json"]) == stage_root / snapshot["active_json"]
        external = json.loads(target.read_text(encoding="utf-8"))
        differences.extend(manifest_annotation_differences(external, snapshot["sidecar_fields"], target.parent, name + "外部"))
        for relative, fields in snapshot["embedded_fields"].items():
            member = stage_root / relative
            embedded = read_image_json(member)
            assert embedded is not None
            differences.extend(manifest_annotation_differences(embedded, fields, member.parent, name + str(relative)))
        for relative in snapshot.get("no_image_stem_sidecar_created", []):
            assert not (stage_root / relative).exists()
        for relative in {**snapshot.get("protected_json", {}), **snapshot.get("original_json_unchanged", {})}:
            assert (stage_root / relative).read_bytes() == originals[Path(relative)]
    for relative in initial.get("protected_json", {}):
        assert (clone / relative).read_bytes() == originals[Path(relative)]
    if "reopened_shapes" in expected:
        shapes = [{**shape, **shape.get("other_data", {})} for shape in stages[-1]["canvas_shapes"]]
        differences.extend(manifest_annotation_differences({"shapes": shapes}, {"shapes": expected["reopened_shapes"]}, clone, "重开画布"))
        if stages[-1]["flags"] != expected["reopened_flags"]:
            differences.append(f"重开 flags：{stages[-1]['flags']!r}，预期 {expected['reopened_flags']!r}")
    if "after_clear" in expected:
        cleared = expected["after_clear"]
        for relative in cleared["absent_json"]:
            assert not (clone / relative).exists()
        for relative in cleared["no_embedded_annotations"]:
            assert read_image_json(clone / relative) is None
        for relative in cleared["original_json_unchanged"]:
            assert (clone / relative).read_bytes() == originals[Path(relative)]
        assert stages[-1]["canvas_shapes"] == [] and stages[-1]["flags"] == cleared["reopened_flags"]
        assert stages[-1]["active_json"] is None
        reopened = next(item for item in stages if item["name"] == "重开主窗口")
        if reopened["flags"] != expected["snapshots"][-1]["sidecar_fields"]["flags"]:
            differences.append(f"组重开 flags：{reopened['flags']!r}，预期 {expected['snapshots'][-1]['sidecar_fields']['flags']!r}")
    if case_id == "L06-valid-empty":
        assert stages[-1]["canvas_shapes"] == expected["empty_canvas_shapes"] == []
        assert stages[-1]["flags"] == expected["flags"]
        assert Path(stages[-1]["active_json"]) == Path(stages[-1]["material_root"]) / expected["active_json"]
    assert not differences, "\n".join(differences)


@pytest.fixture
def screenshot_qt_context(qapp, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from qtpy import QtCore, QtWidgets
    from labelme import __main__ as entrypoint
    from labelme.dlcv import dlcv_tr
    from labelme.dlcv.store import STORE

    try:
        previous_window = STORE.main_window
    except AssertionError:
        previous_window = None
    previous_translator = STORE.q_translator
    base_window = entrypoint.MainWindow
    state = {}
    class ExistingApplication:
        def __new__(cls, arguments):
            return qapp
        @staticmethod
        def instance():
            return qapp
    monkeypatch.setattr(entrypoint, "QtWidgets", SimpleNamespace(QApplication=ExistingApplication, QMessageBox=QtWidgets.QMessageBox))
    monkeypatch.setattr(entrypoint, "native_screenshot_desktop", lambda: "LabelmeScreenshot_owned")
    monkeypatch.setattr(entrypoint, "save_native_screenshot", lambda *args: None)
    monkeypatch.setattr(dlcv_tr, "lang", None)
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(key, os.environ.get(key, str(tmp_path)))
    yield entrypoint, base_window, state
    window = state.get("window")
    if window is not None:
        window.setClean()
        base_window.close(window)
        window.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    STORE.register_main_window(previous_window)
    STORE.q_translator = previous_translator


@pytest.mark.parametrize("fault", ["close_exception", "sync_exception", "settings_status", "developer_status"])
def test_capture_close_sync_failure_is_reported_and_cleans_configuration(monkeypatch, tmp_path, screenshot_qt_context, fault):
    from qtpy import QtCore

    entrypoint, base_window, state = screenshot_qt_context
    materials = tmp_path / "materials"
    materials.mkdir()
    image = materials / "sample.png"
    Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
    image.with_suffix(".json").write_text(json.dumps(capture_annotation(image)), encoding="utf-8")
    output = tmp_path / "capture"
    output.mkdir()
    class ObservedWindow(base_window):
        def __init__(self, *args, **kwargs):
            state["window"] = self
            state["configuration"] = Path(self.settings.fileName()).parent
            super().__init__(*args, **kwargs)
        def close(self):
            state["alive_at_close"] = state["configuration"].is_dir()
            value = super().close()
            state["closed"] = True
            if fault == "close_exception":
                raise RuntimeError("测试关闭失败")
            return value
    original_sync, original_status = QtCore.QSettings.sync, QtCore.QSettings.status
    def sync(settings):
        if state.get("closed") and fault == "sync_exception":
            raise RuntimeError("测试同步失败")
        return original_sync(settings)
    def status(settings):
        if state.get("closed"):
            if fault == "settings_status" and settings is state["window"].settings:
                return QtCore.QSettings.AccessError
            if fault == "developer_status" and settings is state["window"].dev_setting:
                return QtCore.QSettings.AccessError
        return original_status(settings)
    monkeypatch.setattr(entrypoint, "MainWindow", ObservedWindow)
    monkeypatch.setattr(QtCore.QSettings, "sync", sync)
    monkeypatch.setattr(QtCore.QSettings, "status", status)
    reason = "测试关闭失败" if fault == "close_exception" else "测试同步失败" if fault == "sync_exception" else "隔离 INI 保存失败"
    with pytest.raises(RuntimeError, match=reason):
        entrypoint.render_screenshots(str(image), str(output), native=True)
    report = json.loads((output / "场景结果.json").read_text(encoding="utf-8"))
    assert report["success"] is False and reason in report["failure"]
    assert state["alive_at_close"] is True
    assert not state["configuration"].exists()


def test_offscreen_actual_error_dialog_and_owned_timer_are_destroyed(monkeypatch, tmp_path, screenshot_qt_context):
    from qtpy import QtCore, QtWidgets
    from PyQt5 import sip

    entrypoint, base_window, state = screenshot_qt_context
    materials = tmp_path / "materials"
    materials.mkdir()
    image = materials / "sample.png"
    Image.new("RGB", (96, 64), (20, 80, 160)).save(image)
    image.with_suffix(".json").write_text("{", encoding="utf-8")
    output = tmp_path / "capture"
    output.mkdir()
    dialogs, timers, destroyed = [], [], []
    class ObservedDialog(QtWidgets.QMessageBox):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            dialogs.append(self)
            self.destroyed.connect(lambda: destroyed.append("dialog"))
        def exec_(self):
            pytest.fail("离屏错误对话框不能进入原生显示事件")
        def showEvent(self, event):
            pytest.fail("离屏错误对话框不能进入原生显示事件")
        def render(self, *args, **kwargs):
            assert self.icon() == QtWidgets.QMessageBox.Critical
            assert self.standardButtons() == QtWidgets.QMessageBox.Ok
            assert "打开文件发生错误" == self.windowTitle()
            assert "Expecting property name" in self.text()
            owned = self.findChildren(QtCore.QTimer)
            assert len(owned) == 1 and owned[0].parent() is self
            assert owned[0].isSingleShot() and not owned[0].isActive()
            timers.extend(owned)
            return super().render(*args, **kwargs)
    class ObservedWindow(base_window):
        def __init__(self, *args, **kwargs):
            state["window"] = self
            super().__init__(*args, **kwargs)
    monkeypatch.setattr(entrypoint, "MainWindow", ObservedWindow)
    entrypoint.QtWidgets.QMessageBox = ObservedDialog
    entrypoint.render_screenshots(str(image), str(output), case="invalid-json")
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert len(dialogs) == len(timers) == len(destroyed) == 1
    assert sip.isdeleted(dialogs[0]) and sip.isdeleted(timers[0])
    report = json.loads((output / "场景结果.json").read_text(encoding="utf-8"))
    assert report["success"] is True and report["dialog_capture_errors"] == []
    assert "Expecting property name" in report["errors"][0]["message"]
    with Image.open(output / "错误提示.png") as screenshot:
        assert screenshot.width > 200 and screenshot.height > 100
        assert any(low != high for low, high in screenshot.getextrema())


@pytest.mark.parametrize("case_id", ["L01-explicit-json", "L01-image-outputdir"])
def test_manifest_l01_opens_before_import_and_does_not_reopen(monkeypatch, tmp_path, screenshot_manifest, screenshot_qt_context, case_id):
    entrypoint, base_window, state = screenshot_qt_context
    manifest, data = screenshot_manifest
    case = next(item for item in data["cases"] if item["id"] == case_id)
    output = tmp_path / "capture"
    output.mkdir()
    events = []
    original_load, original_import = base_window.loadFile, base_window.importDirImages
    def load(window, filename=None):
        events.append(("load", Path(filename).resolve()))
        return original_load(window, filename)
    def import_images(window, directory, *args, **kwargs):
        events.append(("import", Path(directory).resolve()))
        return original_import(window, directory, *args, **kwargs)
    class InitialCaptured(Exception):
        pass
    def capture(window, directory, name):
        assert name in ("初始主窗口.png", "导入目录后主窗口.png")
        if name == "导入目录后主窗口.png":
            raise InitialCaptured
    class ObservedWindow(base_window):
        def __init__(self, *args, **kwargs):
            state["window"] = self
            super().__init__(*args, **kwargs)
    monkeypatch.setattr(base_window, "loadFile", load)
    monkeypatch.setattr(base_window, "importDirImages", import_images)
    # 调用顺序用例不展示对话框；正式本任务 Discard 由七场景原生运行核验。
    monkeypatch.setattr(base_window, "mayContinue", lambda window: True)
    monkeypatch.setattr(entrypoint, "MainWindow", ObservedWindow)
    monkeypatch.setattr(entrypoint, "save_native_screenshot", capture)
    with pytest.raises(InitialCaptured):
        entrypoint.render_screenshots(None, str(output), native=True, case=case_id, manifest_path=manifest)
    selected = case["inputs"]["selected_json"] if case_id == "L01-explicit-json" else case["inputs"]["image"]
    assert events == [("load", (output / "材料副本" / selected).resolve()),
        ("import", (output / "材料副本" / case["inputs"]["images_directory"]).resolve())]
