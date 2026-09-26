"""新标注存储设置的实际界面离屏证据测试。"""

import json
import os
from pathlib import Path

import pytest
from PIL import Image
from PIL import ImageDraw
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets


FULL_IMAGE_SIZE = QtCore.QSize(1920, 1080)


def _configure_isolated_environment(monkeypatch, tmp_path):
    isolated_paths = {
        "HOME": tmp_path / "home",
        "USERPROFILE": tmp_path / "home",
        "APPDATA": tmp_path / "appdata",
        "LOCALAPPDATA": tmp_path / "localappdata",
        "XDG_CONFIG_HOME": tmp_path / "xdg-config",
        "XDG_CACHE_HOME": tmp_path / "xdg-cache",
        "TEMP": tmp_path / "temp",
        "TMP": tmp_path / "temp",
    }
    for path in set(isolated_paths.values()):
        path.mkdir(parents=True, exist_ok=True)
    for name, path in isolated_paths.items():
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_OPENGL", "software")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "-1")

    settings_path = tmp_path / "qsettings"
    settings_path.mkdir()
    previous_format = QtCore.QSettings.defaultFormat()
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
    for scope in (QtCore.QSettings.UserScope, QtCore.QSettings.SystemScope):
        QtCore.QSettings.setPath(
            QtCore.QSettings.IniFormat,
            scope,
            str(settings_path),
        )
    return isolated_paths, settings_path, previous_format


def _configure_cjk_font(app):
    candidates = []
    windows_dir = os.environ.get("WINDIR")
    if windows_dir:
        fonts_dir = Path(windows_dir) / "Fonts"
        candidates.extend(
            [
                fonts_dir / "msyh.ttc",
                fonts_dir / "msyhbd.ttc",
                fonts_dir / "simhei.ttf",
                fonts_dir / "simsun.ttc",
            ]
        )
    candidates.extend(
        [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            Path("/System/Library/Fonts/PingFang.ttc"),
        ]
    )

    for font_path in candidates:
        if not font_path.is_file():
            continue
        font_id = QtGui.QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            continue
        families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
        if families:
            font = QtGui.QFont(families[0], 10)
            app.setFont(font)
            return families[0], str(font_path)
    pytest.fail("缺少可用于 Qt 离屏中文渲染的系统字体")


def _create_sample_annotation(tmp_path, label_file_class):
    image_path = tmp_path / "annotation-storage-sample.png"
    image = Image.new("RGB", (1280, 720), (31, 50, 72))
    painter = ImageDraw.Draw(image)
    painter.rectangle((150, 130, 530, 460), outline=(51, 214, 166), width=8)
    painter.rectangle((680, 190, 1080, 570), outline=(255, 183, 77), width=8)
    image.save(image_path)

    shapes = [
        {
            "label": "缺陷-A",
            "points": [[150, 130], [530, 130], [530, 460], [150, 460]],
            "group_id": None,
            "description": "",
            "shape_type": "polygon",
            "flags": {},
            "mask": None,
        },
        {
            "label": "缺陷-B",
            "points": [[680, 190], [1080, 190], [1080, 570], [680, 570]],
            "group_id": None,
            "description": "",
            "shape_type": "polygon",
            "flags": {},
            "mask": None,
        },
    ]
    external_json_path = image_path.with_suffix(".json")
    label_file_class().save(
        str(external_json_path),
        shapes,
        image_path.name,
        720,
        1280,
        imageData=None,
        otherData={},
        flags={},
        save_external_json=True,
    )

    external_data = json.loads(external_json_path.read_text(encoding="utf-8"))
    external_data["shapes"] = [
        {
            **shapes[0],
            "label": "外部旧数据",
        }
    ]
    external_json_path.write_text(
        json.dumps(external_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return image_path, external_json_path, shapes


def _process_events(app, count=12):
    for _ in range(count):
        app.processEvents()


def _close_window(app, window):
    if window is None:
        return
    window.close()
    window.deleteLater()
    _process_events(app, 4)


def _prepare_evidence_layout(window):
    for name in ("flag_dock", "shape_dock", "label_dock"):
        dock = getattr(window, name, None)
        if dock is not None:
            dock.hide()

    for dock in (window.label_count_dock, window.setting_dock):
        window.removeDockWidget(dock)
        dock.setFloating(False)
        dock.setMinimumWidth(500)
        window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        dock.show()
    window.splitDockWidget(
        window.label_count_dock,
        window.setting_dock,
        QtCore.Qt.Vertical,
    )

    parameters = window.setting_dock.parameter
    for group in parameters.children():
        group.setOpts(expanded=group.name() == "proj_setting")
    window.setting_dock.parameter_tree.setColumnWidth(0, 320)

    window.label_count_dock.count_labels_in_file(window.canvas.shapes, {})
    window.resize(FULL_IMAGE_SIZE)
    window.show()
    window.resize(FULL_IMAGE_SIZE)
    app = QtWidgets.QApplication.instance()
    _process_events(app)
    window.resizeDocks(
        [window.label_count_dock, window.setting_dock],
        [440, 360],
        QtCore.Qt.Vertical,
    )
    _process_events(app)


def _render_widget(widget, path):
    image = QtGui.QImage(widget.size(), QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)
    widget.render(image)
    assert not image.isNull()
    assert image.width() >= 1920
    assert image.height() >= 1000
    assert image.save(str(path))
    assert path.is_file()
    assert path.stat().st_size > 10_000
    reader = QtGui.QImageReader(str(path))
    assert reader.canRead()
    assert reader.size() == widget.size()
    return image


def _save_settings_panel_crop(full_image, window, path):
    rect = window.label_count_dock.geometry().united(window.setting_dock.geometry())
    rect = rect.adjusted(-8, -8, 0, 0).intersected(full_image.rect())
    panel_image = full_image.copy(rect)
    assert not panel_image.isNull()
    assert panel_image.width() >= 480
    assert panel_image.height() >= 700
    assert panel_image.save(str(path))
    assert path.stat().st_size > 5_000
    return panel_image


def test_annotation_storage_setting_main_window_render(monkeypatch, tmp_path):
    """实际 MainWindow 保存、恢复并渲染新存储设置。"""
    isolated_paths, settings_path, previous_format = _configure_isolated_environment(
        monkeypatch,
        tmp_path,
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    previous_font = QtGui.QFont(app.font())
    font_family = None
    font_path = None
    first_window = None
    evidence_window = None

    try:
        font_family, font_path = _configure_cjk_font(app)

        from dlcv_core.image_json import read_image_json
        from labelme.config import get_config
        from labelme.dlcv import dlcv_tr
        from labelme.dlcv.app import MainWindow
        from labelme.dlcv.label_file import LabelFile

        dlcv_tr.set_lang("zh_CN")
        default_config = get_config()
        assert default_config["save_external_json"] is True

        settings = QtCore.QSettings("labelme", "labelme")
        settings.clear()
        settings.setValue("ui/theme", "modern")
        settings.setValue("ui/language", "zh_CN")
        settings.setValue("setting_store", {"save_external_json": False})
        settings.sync()
        assert settings.status() == QtCore.QSettings.NoError

        image_path, external_json_path, expected_shapes = _create_sample_annotation(
            tmp_path,
            LabelFile,
        )
        assert external_json_path.is_file()
        embedded_data = read_image_json(image_path)
        external_data = json.loads(
            external_json_path.read_text(encoding="utf-8")
        )
        assert [shape["label"] for shape in external_data["shapes"]] == [
            "外部旧数据"
        ]
        assert [shape["label"] for shape in embedded_data["shapes"]] == [
            shape["label"] for shape in expected_shapes
        ]

        first_window = MainWindow(config=get_config(), filename=str(image_path))
        first_window.resize(FULL_IMAGE_SIZE)
        first_window.show()
        _process_events(app)
        assert len(first_window.canvas.shapes) == 2
        restored_parameter = first_window.setting_dock.parameter.child(
            "proj_setting",
            "save_external_json",
        )
        assert restored_parameter.value() is False
        initial_restored_value = restored_parameter.value()
        assert first_window._config["save_external_json"] is False

        restored_parameter.setValue(True)
        assert first_window._config["save_external_json"] is True
        _close_window(app, first_window)
        first_window = None

        persisted_settings = QtCore.QSettings("labelme", "labelme")
        persisted_store = persisted_settings.value("setting_store")
        assert isinstance(persisted_store, dict)
        assert persisted_store["save_external_json"] is True

        evidence_window = MainWindow(config=get_config(), filename=str(image_path))
        evidence_window.resize(FULL_IMAGE_SIZE)
        evidence_window.show()
        _process_events(app)
        setting_parameter = evidence_window.setting_dock.parameter.child(
            "proj_setting",
            "save_external_json",
        )
        assert setting_parameter.opts["title"] == "同时保存外部 JSON"
        assert setting_parameter.value() is True
        assert evidence_window._config["save_external_json"] is True
        assert len(evidence_window.canvas.shapes) == 2
        assert [shape.label for shape in evidence_window.canvas.shapes] == [
            "缺陷-A",
            "缺陷-B",
        ]

        _prepare_evidence_layout(evidence_window)
        count_text = evidence_window.label_count_dock.label_count_text.toPlainText()
        assert "缺陷-A: 1" in count_text
        assert "缺陷-B: 1" in count_text
        assert "标签总数: 2" in count_text
        assert "总数: 2" in count_text
        assert evidence_window.setting_dock.isVisible()
        assert evidence_window.label_count_dock.isVisible()

        setting_items = [
            item
            for item in evidence_window.setting_dock.parameter_tree.listAllItems()
            if getattr(item, "param", None) is setting_parameter
        ]
        assert len(setting_items) == 1
        assert setting_items[0].text(0) == "同时保存外部 JSON"
        assert not setting_items[0].isHidden()

        artifact_dir = Path(os.environ.get("DLCV_UI_ARTIFACT_DIR", tmp_path))
        artifact_dir.mkdir(parents=True, exist_ok=True)
        full_path = artifact_dir / "annotation_storage_settings_full.png"
        panel_path = artifact_dir / "annotation_storage_settings_panel.png"
        result_path = artifact_dir / "annotation_storage_settings_result.json"

        full_image = _render_widget(evidence_window, full_path)
        panel_image = _save_settings_panel_crop(
            full_image,
            evidence_window,
            panel_path,
        )

        result = {
            "window_class": (
                f"{type(evidence_window).__module__}."
                f"{type(evidence_window).__name__}"
            ),
            "setting_dock_class": (
                f"{type(evidence_window.setting_dock).__module__}."
                f"{type(evidence_window.setting_dock).__name__}"
            ),
            "setting_title": setting_parameter.opts["title"],
            "default_save_external_json": default_config["save_external_json"],
            "initial_restored_save_external_json": initial_restored_value,
            "final_restored_save_external_json": setting_parameter.value(),
            "persisted_save_external_json": persisted_store["save_external_json"],
            "external_json_exists": external_json_path.is_file(),
            "external_labels": [
                shape["label"] for shape in external_data["shapes"]
            ],
            "embedded_labels": [
                shape["label"] for shape in embedded_data["shapes"]
            ],
            "loaded_annotation_source": "embedded",
            "loaded_labels": [
                shape.label for shape in evidence_window.canvas.shapes
            ],
            "loaded_label_count": len(evidence_window.canvas.shapes),
            "label_count_text": count_text,
            "full_screenshot": {
                "path": str(full_path),
                "width": full_image.width(),
                "height": full_image.height(),
                "bytes": full_path.stat().st_size,
            },
            "settings_panel_screenshot": {
                "path": str(panel_path),
                "width": panel_image.width(),
                "height": panel_image.height(),
                "bytes": panel_path.stat().st_size,
            },
            "font_family": font_family,
            "font_path": font_path,
            "isolated_home": str(isolated_paths["HOME"]),
            "isolated_appdata": str(isolated_paths["APPDATA"]),
            "isolated_qsettings": str(settings_path),
            "temporary_data_root": str(tmp_path),
        }
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        assert result_path.stat().st_size > 500
    finally:
        _close_window(app, first_window)
        _close_window(app, evidence_window)
        app.setFont(previous_font)
        QtCore.QSettings.setDefaultFormat(previous_format)
