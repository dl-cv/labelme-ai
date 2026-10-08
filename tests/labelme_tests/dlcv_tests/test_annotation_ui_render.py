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
    destroyed = []
    objects = [
        window,
        window.menus.labelList,
        window.menus.recentFiles,
        *window.canvas.menus,
    ]
    for obj in objects:
        obj.destroyed.connect(lambda: destroyed.append(True))
    window.close()
    window.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(window, QtCore.QEvent.DeferredDelete)
    assert len(destroyed) == len(objects), "关闭窗口后应销毁窗口及所属菜单"
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


def test_annotation_storage_setting_main_window_render(monkeypatch, tmp_path, qapp):
    """实际 MainWindow 保存、恢复并渲染新存储设置。"""
    isolated_paths, settings_path, previous_format = _configure_isolated_environment(
        monkeypatch,
        tmp_path,
    )
    app = qapp
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
        external_data = json.loads(external_json_path.read_text(encoding="utf-8"))
        assert [shape["label"] for shape in external_data["shapes"]] == ["外部旧数据"]
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
                f"{type(evidence_window).__module__}.{type(evidence_window).__name__}"
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
            "external_labels": [shape["label"] for shape in external_data["shapes"]],
            "embedded_labels": [shape["label"] for shape in embedded_data["shapes"]],
            "loaded_annotation_source": "embedded",
            "loaded_labels": [shape.label for shape in evidence_window.canvas.shapes],
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


@pytest.fixture
def annotation_window(monkeypatch, tmp_path, qapp):
    """隔离设置和图片，运行实际标注窗口的保存流程。"""
    _, _, previous_format = _configure_isolated_environment(monkeypatch, tmp_path)
    app = qapp
    app.setQuitOnLastWindowClosed(False)
    window = None
    try:
        from labelme.config import get_config
        from labelme.dlcv.app import MainWindow
        from labelme.dlcv.label_file import LabelFile

        settings = QtCore.QSettings("labelme", "labelme")
        settings.clear()
        settings.setValue("ui/language", "zh_CN")
        settings.sync()
        image_dir = tmp_path / "images"
        image_dir.mkdir()
        image_path, sidecar_path, _ = _create_sample_annotation(image_dir, LabelFile)
        other_path = image_dir / "unannotated.png"
        Image.new("RGB", (1280, 720), (60, 70, 80)).save(other_path)
        config = get_config()
        config["auto_save"] = False
        config["keep_prev"] = False
        window = MainWindow(config=config, filename=str(image_path))
        window.actions.saveAuto.setChecked(False)
        window.importDirImages(str(image_dir), load=False)
        window.loadFile(str(image_path))
        window.show()
        _process_events(app)
        assert len(window.canvas.shapes) == 2
        yield app, window, image_path, sidecar_path, other_path
    finally:
        if window is not None:
            window.setClean()
        _close_window(app, window)
        QtCore.QSettings.setDefaultFormat(previous_format)


@pytest.mark.parametrize("save_external", [True, False])
def test_main_window_edit_save_switch_and_reopen(annotation_window, save_external):
    from dlcv_core.image_json import read_image_json

    app, window, image_path, sidecar_path, other_path = annotation_window
    parameter = window.setting_dock.parameter.child(
        "proj_setting", "save_external_json"
    )
    parameter.setValue(save_external)
    if not save_external:
        sidecar_path.unlink()
    expected_points = [
        [[175, 145], [530, 130], [530, 460], [150, 460]],
        [[680, 190], [1080, 190], [1080, 570], [680, 570]],
    ]
    window.canvas.shapes[0].label = "编辑后的标注"
    window.canvas.shapes[0].points[0] = QtCore.QPointF(175, 145)
    window.setDirty()
    assert window.dirty
    window.saveFile()
    assert not window.dirty
    assert not window.actions.save.isEnabled()
    embedded = read_image_json(image_path)
    assert embedded["shapes"][0]["label"] == "编辑后的标注"
    assert [shape["points"] for shape in embedded["shapes"]] == expected_points
    assert (embedded["imageWidth"], embedded["imageHeight"]) == (1280, 720)
    assert embedded["imagePath"] == image_path.name
    assert (image_path.parent / embedded["imagePath"]).resolve() == image_path.resolve()
    assert sidecar_path.exists() is save_external
    if save_external:
        external = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert external["shapes"][0]["label"] == "编辑后的标注"
        assert [shape["points"] for shape in external["shapes"]] == expected_points
        assert (external["imageWidth"], external["imageHeight"]) == (1280, 720)
        assert (
            sidecar_path.parent / external["imagePath"]
        ).resolve() == image_path.resolve()
    window.loadFile(str(other_path))
    _process_events(app)
    assert window.filename == str(other_path)
    assert window.canvas.shapes == []
    window.loadFile(str(image_path))
    _process_events(app)
    assert window.filename == str(image_path)
    assert [shape.label for shape in window.canvas.shapes] == ["编辑后的标注", "缺陷-B"]
    assert [
        [list((p.x(), p.y())) for p in shape.points] for shape in window.canvas.shapes
    ] == expected_points
    assert (window.image.width(), window.image.height()) == (1280, 720)
    assert Path(window.imagePath).resolve() == image_path.resolve()
    assert window.labelFile.imagePath == image_path.name
    window.canvas.shapes[1].label = "再次编辑"
    window.setDirty()
    window.saveFile()
    window.loadFile(str(other_path))
    window.loadFile(str(image_path))
    assert [shape.label for shape in window.canvas.shapes] == [
        "编辑后的标注",
        "再次编辑",
    ]
    assert [
        [list((p.x(), p.y())) for p in shape.points] for shape in window.canvas.shapes
    ] == expected_points
    assert (window.image.width(), window.image.height()) == (1280, 720)
    assert Path(window.imagePath).resolve() == image_path.resolve()
    saved = read_image_json(image_path)
    assert [shape["points"] for shape in saved["shapes"]] == expected_points
    assert (saved["imageWidth"], saved["imageHeight"]) == (1280, 720)
    assert saved["imagePath"] == image_path.name


@pytest.mark.parametrize("save_external", [True, False])
def test_main_window_annotation_filter_and_clear(annotation_window, save_external):
    from dlcv_core.image_json import read_image_json

    app, window, image_path, sidecar_path, other_path = annotation_window
    window.setting_dock.parameter.child("proj_setting", "save_external_json").setValue(
        save_external
    )
    if not save_external:
        sidecar_path.unlink()
    window.canvas.shapes[0].label = "已保存标注"
    window.setDirty()
    window.saveFile()
    assert sidecar_path.exists() is save_external
    tree = window.fileListWidget
    image_item = tree.findItems(str(image_path))[0]
    other_item = tree.findItems(str(other_path))[0]
    assert image_item.checkState(0) == QtCore.Qt.Checked
    assert other_item.checkState(0) == QtCore.Qt.Unchecked
    tree.show_annotated_checkbox.setChecked(True)
    tree.show_unannotated_checkbox.setChecked(False)
    _process_events(app)
    assert not image_item.isHidden()
    assert other_item.isHidden()
    window.canvas.selectShapes(window.canvas.shapes)
    window.deleteSelectedShape()
    window.saveFile()
    _process_events(app)
    assert read_image_json(image_path) is None
    assert not sidecar_path.exists()
    assert window.canvas.shapes == []
    assert image_item.checkState(0) == QtCore.Qt.Unchecked
    assert image_item.isHidden()
    assert not window.dirty
    tree.show_annotated_checkbox.setChecked(False)
    tree.show_unannotated_checkbox.setChecked(True)
    _process_events(app)
    assert not image_item.isHidden()
    assert not other_item.isHidden()
    window.loadFile(str(other_path))
    window.loadFile(str(image_path))
    assert window.canvas.shapes == []


@pytest.mark.parametrize("save_external", [True, False])
def test_main_window_readonly_save_keeps_edits(
    annotation_window, monkeypatch, save_external
):
    """图片实际只读时保留当前编辑，恢复写权限后可继续保存。"""
    import stat

    from dlcv_core.image_json import read_image_json

    app, window, image_path, sidecar_path, _ = annotation_window
    errors = []
    monkeypatch.setattr(
        window, "errorMessage", lambda title, text: errors.append((title, text))
    )
    window.setting_dock.parameter.child("proj_setting", "save_external_json").setValue(
        save_external
    )
    before = image_path.read_bytes()
    window.canvas.shapes[0].label = "未保存的编辑"
    window.setDirty()
    original_mode = image_path.stat().st_mode
    try:
        image_path.chmod(stat.S_IREAD)
        window.saveFile()
        _process_events(app)
        assert errors
        assert window.dirty
        assert window.actions.save.isEnabled()
        assert window.filename == str(image_path)
        assert window.canvas.shapes[0].label == "未保存的编辑"
        assert image_path.read_bytes() == before
        assert (
            json.loads(sidecar_path.read_text(encoding="utf-8"))["shapes"][0]["label"]
            == "未保存的编辑"
        )
    finally:
        image_path.chmod(original_mode)
    window.saveFile()
    assert not window.dirty
    assert read_image_json(image_path)["shapes"][0]["label"] == "未保存的编辑"


@pytest.mark.parametrize("malformed", [None, [], {"shapes": "错误结构"}])
def test_main_window_external_only_and_corrupt_embedded(
    annotation_window, monkeypatch, malformed
):
    from dlcv_core.image_json import remove_image_json
    from dlcv_core.image_json import write_image_json

    app, window, image_path, sidecar_path, other_path = annotation_window
    remove_image_json(image_path)
    window.loadFile(str(other_path))
    window.loadFile(str(image_path))
    _process_events(app)
    assert [shape.label for shape in window.canvas.shapes] == ["外部旧数据"]
    assert window.labelFile.filename == str(sidecar_path)
    window.canvas.shapes[0].label = "外部文件编辑"
    window.setDirty()
    window.saveFile()
    assert (
        json.loads(sidecar_path.read_text(encoding="utf-8"))["shapes"][0]["label"]
        == "外部文件编辑"
    )
    window.loadFile(str(other_path))
    errors = []
    monkeypatch.setattr(
        window, "errorMessage", lambda title, text: errors.append((title, text))
    )
    write_image_json(image_path, malformed)
    assert window.loadFile(str(image_path)) is False
    assert errors
    assert window.canvas.shapes == []
    assert window.filename == str(image_path)


def test_main_window_manual_save_keeps_custom_sidecar(annotation_window):
    from dlcv_core.image_json import read_image_json

    app, window, image_path, sidecar_path, other_path = annotation_window
    custom_path = image_path.parent / "labels" / "custom.json"
    expected_points = [
        [[150, 130], [530, 130], [530, 460], [150, 460]],
        [[680, 190], [1080, 190], [1080, 570], [680, 570]],
    ]
    window.canvas.shapes[0].label = "另存数据"
    window.setDirty()
    window._saveFile(str(custom_path))
    first_default = sidecar_path.read_bytes()
    window.canvas.shapes[0].label = "后续保存"
    window.setDirty()
    window.saveFile()
    assert not window.dirty
    external = json.loads(custom_path.read_text(encoding="utf-8"))
    assert external["shapes"][0]["label"] == "后续保存"
    assert not Path(external["imagePath"]).is_absolute()
    assert (
        custom_path.parent / external["imagePath"]
    ).resolve() == image_path.resolve()
    assert [shape["points"] for shape in external["shapes"]] == expected_points
    assert (external["imageWidth"], external["imageHeight"]) == (1280, 720)
    assert sidecar_path.read_bytes() == first_default
    embedded = read_image_json(image_path)
    assert embedded["shapes"][0]["label"] == "后续保存"
    assert embedded["imagePath"] == image_path.name
    assert [shape["points"] for shape in embedded["shapes"]] == expected_points
    assert (embedded["imageWidth"], embedded["imageHeight"]) == (1280, 720)
    window.loadFile(str(other_path))
    window.loadFile(str(image_path))
    _process_events(app)
    assert window.canvas.shapes[0].label == "后续保存"
    assert Path(window.imagePath).resolve() == image_path.resolve()
    assert (window.image.width(), window.image.height()) == (1280, 720)
    assert [
        [list((p.x(), p.y())) for p in shape.points] for shape in window.canvas.shapes
    ] == expected_points


@pytest.mark.parametrize("operation", ["switch", "close", "output_file", "cancel"])
def test_main_window_failed_save_prevents_switch_and_close(
    annotation_window, monkeypatch, operation
):
    """实际只读图片保存失败后，不切图、不退出且保留完整编辑。"""
    import stat

    from dlcv_core.image_json import read_image_json

    app, window, image_path, _, other_path = annotation_window
    errors = []
    monkeypatch.setattr(
        window, "errorMessage", lambda title, text: errors.append((title, text))
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "question", lambda *args: QtWidgets.QMessageBox.Save
    )
    if operation == "switch":
        window.loadFile(image_path.as_posix())
        navigate = (
            window.openNextImg if window.imageList.index(window.filename) == 0
            else window.openPrevImg
        )
    window.canvas.shapes[0].label = "保存失败保留编辑"
    window.canvas.shapes[0].points[0] = QtCore.QPointF(175, 145)
    window.setDirty()
    before_shapes = [
        (shape.label, [(p.x(), p.y()) for p in shape.points])
        for shape in window.canvas.shapes
    ]
    before_image = window.image.copy()
    before_bytes = image_path.read_bytes()
    mode = image_path.stat().st_mode
    try:
        image_path.chmod(stat.S_IREAD)
        if operation == "switch":
            navigate()
        elif operation == "close":
            event = QtGui.QCloseEvent()
            QtWidgets.QApplication.sendEvent(window, event)
            assert not event.isAccepted()
            assert not window.close()
        elif operation == "output_file":
            window.labelFile = None
            window.output_file = str(image_path.parent / "output.json")
            assert window.saveFile() is False
        else:
            window.labelFile = None
            monkeypatch.setattr(window, "saveFileDialog", lambda: "")
            assert window.mayContinue() is False
        _process_events(app)
        assert bool(errors) is (operation != "cancel")
        assert window.isVisible()
        assert Path(window.filename).resolve() == image_path.resolve()
        assert window.image == before_image
        assert window.dirty
        assert window.actions.save.isEnabled()
        assert [
            (shape.label, [(p.x(), p.y()) for p in shape.points])
            for shape in window.canvas.shapes
        ] == before_shapes
        assert image_path.read_bytes() == before_bytes
    finally:
        image_path.chmod(mode)

    if operation == "cancel":
        monkeypatch.setattr(window, "saveFileDialog", lambda: str(image_path.with_suffix(".json")))
    assert window.saveFile()
    assert not window.dirty
    saved = read_image_json(image_path)
    assert saved["shapes"][0]["label"] == "保存失败保留编辑"
    assert [shape["points"] for shape in saved["shapes"]] == [
        [list(point) for point in points] for _, points in before_shapes
    ]
    assert (saved["imageWidth"], saved["imageHeight"]) == (1280, 720)
    if operation == "switch":
        navigate()
        assert Path(window.filename).resolve() == other_path.resolve()
    else:
        assert window.close()
        assert not window.isVisible()


@pytest.mark.parametrize("save_external", [True, False])
def test_main_window_clear_default_and_custom_sidecars(annotation_window, save_external):
    from dlcv_core.image_json import has_image_json

    app, window, image_path, default_path, other_path = annotation_window
    custom_path = image_path.parent / "labels" / "custom.json"
    window.canvas.shapes[0].label = "另存后的标注"
    window.setDirty()
    assert window._saveFile(str(custom_path))
    assert custom_path.exists() and default_path.exists()
    window.setting_dock.parameter.child("proj_setting", "save_external_json").setValue(
        save_external
    )
    tree = window.fileListWidget
    item = tree.findItems(str(image_path))[0]
    tree.show_annotated_checkbox.setChecked(True)
    window.canvas.selectShapes(window.canvas.shapes)
    window.deleteSelectedShape()
    assert window.saveFile()
    _process_events(app)
    assert not custom_path.exists()
    assert not default_path.exists()
    assert not has_image_json(image_path)
    assert item.checkState(0) == QtCore.Qt.Unchecked
    assert item.isHidden()
    assert not window.dirty
    window.loadFile(str(other_path))
    window.loadFile(str(image_path))
    assert Path(window.imagePath).resolve() == image_path.resolve()
    assert (window.image.width(), window.image.height()) == (1280, 720)
    assert window.canvas.shapes == []
    assert not window.hasLabelFile()


@pytest.mark.parametrize("failure", ["corrupt", "missing"])
def test_main_window_and_file_tree_report_annotation_read_failure(
    annotation_window, monkeypatch, failure
):
    from labelme.dlcv import utils_func
    from labelme.dlcv.file_tree_widget import _has_embedded_annotation

    app, window, image_path, sidecar_path, _ = annotation_window
    errors = []
    monkeypatch.setattr(utils_func, "notification", lambda *args: errors.append(args))
    sidecar_path.unlink()
    original = image_path.read_bytes()
    try:
        if failure == "corrupt":
            image_path.write_bytes(original[:16])
        else:
            image_path.unlink()
        assert not window.hasLabelFile()
        assert not _has_embedded_annotation(image_path)
        assert len(errors) == 2
        assert all(str(image_path) in str(args[1]) for args in errors)
        assert all(args[2] == utils_func.ToastPreset.ERROR for args in errors)
    finally:
        image_path.write_bytes(original)


def test_main_window_item_change_filters_only_changed_file(annotation_window, monkeypatch):
    app, window, image_path, _, other_path = annotation_window
    tree = window.fileListWidget
    item = tree.findItems(str(image_path))[0]
    calls = []
    original = window.proj_manager.get_json_path

    def record(img_path):
        calls.append(Path(img_path).resolve())
        return original(img_path)

    monkeypatch.setattr(window.proj_manager, "get_json_path", record)
    item.setCheckState(QtCore.Qt.Unchecked)
    _process_events(app)
    assert calls == []
    tree._apply_filters()
    assert calls == []
    tree.show_annotated_checkbox.setChecked(True)
    calls.clear()
    item.setCheckState(QtCore.Qt.Checked)
    _process_events(app)
    assert calls == [image_path.resolve()]
    assert other_path.resolve() not in calls


def test_main_window_clear_failure_keeps_both_sidecars_and_edits(
    annotation_window, monkeypatch
):
    import stat
    from dlcv_core.image_json import read_image_json

    app, window, image_path, default_path, _ = annotation_window
    custom_path = image_path.parent / "labels" / "custom.json"
    window.canvas.shapes[0].label = "清空前有效标注"
    window.setDirty()
    assert window._saveFile(str(custom_path))
    originals = {path: path.read_bytes() for path in (image_path, default_path, custom_path)}
    window.canvas.selectShapes(window.canvas.shapes)
    window.deleteSelectedShape()
    errors = []
    monkeypatch.setattr(window, "errorMessage", lambda *args: errors.append(args))
    mode = default_path.stat().st_mode
    try:
        default_path.chmod(stat.S_IREAD)
        assert not window.saveFile()
        assert errors and window.dirty and window.actions.save.isEnabled()
        assert window.canvas.shapes == []
        assert {path: path.read_bytes() for path in originals} == originals
        assert read_image_json(image_path)["shapes"][0]["label"] == "清空前有效标注"
    finally:
        default_path.chmod(mode)
    assert window.saveFile()
    assert not default_path.exists() and not custom_path.exists()
    assert read_image_json(image_path) is None


@pytest.mark.parametrize("path_style", ["native", "posix"])
def test_main_window_failed_tree_selection_restores_current_and_retries(
    annotation_window, monkeypatch, path_style
):
    """直接选择文件树节点，保存失败时恢复实际选择，恢复写权限后再次切图。"""
    import stat
    from dlcv_core.image_json import read_image_json

    app, window, image_path, _, other_path = annotation_window
    tree = window.fileListWidget
    original_item = tree.findItems(str(image_path))[0]
    other_item = tree.findItems(str(other_path))[0]
    window.setClean()
    tree.setCurrentItem(original_item)
    window.loadFile(str(image_path) if path_style == "native" else image_path.as_posix())
    assert tree.currentItem() is original_item
    assert tree.selectedItems() == [original_item]
    errors = []
    questions = []
    monkeypatch.setattr(window, "errorMessage", lambda *args: errors.append(args))

    def choose_save(*args):
        questions.append(True)
        return QtWidgets.QMessageBox.Save

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", choose_save)
    window.canvas.shapes[0].label = "列表切图失败保留编辑"
    window.canvas.shapes[0].points[0] = QtCore.QPointF(175, 145)
    window.setDirty()
    before_shapes = [
        (shape.label, [(p.x(), p.y()) for p in shape.points])
        for shape in window.canvas.shapes
    ]
    before_image = window.image.copy()
    before_bytes = image_path.read_bytes()
    mode = image_path.stat().st_mode
    try:
        image_path.chmod(stat.S_IREAD)
        tree.setCurrentItem(other_item)
        _process_events(app)
        assert len(questions) == 1 and len(errors) == 1
        assert Path(window.filename).resolve() == image_path.resolve()
        assert tree.currentItem() is original_item
        assert tree.selectedItems() == [original_item]
        assert not other_item.isSelected()
        assert window.image == before_image
        assert window.dirty and window.actions.save.isEnabled()
        assert [
            (shape.label, [(p.x(), p.y()) for p in shape.points])
            for shape in window.canvas.shapes
        ] == before_shapes
        assert image_path.read_bytes() == before_bytes
    finally:
        image_path.chmod(mode)

    tree.setCurrentItem(other_item)
    _process_events(app)
    assert len(questions) == 2 and len(errors) == 1
    assert tree.currentItem() is other_item
    assert tree.selectedItems() == [other_item]
    assert Path(window.filename).resolve() == other_path.resolve()
    assert window.canvas.shapes == []
    # 既有 loadFile 在加载结束调用 setDirty；上一图是否保存由实际内嵌内容证明。
    assert window.dirty
    saved = read_image_json(image_path)
    assert saved["shapes"][0]["label"] == "列表切图失败保留编辑"
    assert [shape["points"] for shape in saved["shapes"]] == [
        [list(point) for point in points] for _, points in before_shapes
    ]
    assert (saved["imageWidth"], saved["imageHeight"]) == (1280, 720)
