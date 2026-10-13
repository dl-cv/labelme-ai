"""启动报告必须来自实际窗口绘制，且拒绝覆盖已有结果。"""

import json
import os
from pathlib import Path

import pytest

from labelme.startup import StartupReport, configure_startup_report


@pytest.mark.skipif(os.name != "nt", reason="Windows 进程时间接口")
@pytest.mark.parametrize("with_image", [False, True])
def test_report_after_real_window_paint(qtbot, tmp_path, with_image):
    from labelme.config import get_config
    from labelme.dlcv.app import MainWindow

    path = configure_startup_report(tmp_path / "startup.json")
    config = get_config()
    config["auto_save"] = False
    image = Path(__file__).resolve().parents[1] / "examples/instance_segmentation/data_annotated/2011_000003.jpg"
    window = MainWindow(config=config, filename=str(image) if with_image else None)
    qtbot.addWidget(window)
    recorder = StartupReport(window, path)
    assert not path.exists()
    window.show()
    def report_ready():
        assert path.exists(), [
            (widget.metaObject().className(), widget.objectName())
            for widget in recorder.pending
        ]

    qtbot.waitUntil(report_ready)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    assert data["startup_ms"] > 0
    assert data["title"] == window.windowTitle()
    assert data["image_loaded"] is with_image
    assert data["shape_count"] == (5 if with_image else 0)
    assert data["painted_widgets"] > 2
    assert not recorder.pending
    window.repaint()
    assert json.loads(path.read_text(encoding="utf-8")) == data
    assert recorder.parent() is window
    with pytest.raises(ValueError):
        configure_startup_report(path)
    window.setClean()
