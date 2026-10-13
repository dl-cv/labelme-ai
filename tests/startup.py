"""仅供测试使用的主窗口首帧计时器。"""

import ctypes
import json
import os
import time
from pathlib import Path

from qtpy import QtCore, QtWidgets


def process_created_at():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [
        ctypes.POINTER(ctypes.c_uint64)
    ] * 4
    values = [ctypes.c_uint64() for _ in range(4)]
    if not kernel.GetProcessTimes(
        kernel.GetCurrentProcess(), *(ctypes.byref(value) for value in values)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return values[0].value / 10_000_000 - 11_644_473_600


def configure_startup_report(path):
    if os.name != "nt":
        raise ValueError("启动计时目前仅支持 Windows")
    path = Path(path).resolve()
    if not path.parent.is_dir() or path.exists():
        raise ValueError("启动报告需要现有目录中的新文件路径")
    return path


class StartupReport(QtCore.QObject):
    def __init__(self, window, path):
        super().__init__(window)
        self.window = window
        self.path = path
        self.created_at = process_created_at()
        self.pending = {window, window.canvas}
        self.pending.update(
            view.viewport()
            for view in window.findChildren(QtWidgets.QAbstractItemView)
            if view.isVisibleTo(window)
        )
        self.paint_target_count = len(self.pending)
        for widget in self.pending:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched in self.pending and event.type() == QtCore.QEvent.Paint:
            watched.removeEventFilter(self)
            self.pending.remove(watched)
            # 主窗、画布和各列表面板均绘制后，再等最后一次 Paint 返回。
            if not self.pending:
                QtCore.QTimer.singleShot(0, self.record)
        return False

    def record(self):
        ready_at = time.time()
        from labelme import __version__

        data = {
            "version": __version__,
            "pid": os.getpid(),
            "startup_ms": round((ready_at - self.created_at) * 1000, 2),
            "title": self.window.windowTitle(),
            "image_loaded": not self.window.canvas.pixmap.isNull(),
            "shape_count": len(self.window.canvas.shapes),
            "painted_widgets": self.paint_target_count,
        }
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
