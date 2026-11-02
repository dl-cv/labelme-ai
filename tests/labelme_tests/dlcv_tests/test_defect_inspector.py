"""缺陷巡检面板：类别筛选、逐个跳转与自动放大定位检查。"""

import json
from pathlib import Path

import pytest
from PIL import Image
from qtpy.QtCore import Qt

from labelme.config import get_config
from labelme.dlcv.app import MainWindow


def _create_window(qtbot, tmp_path):
    image_path = tmp_path / "defects.png"
    Image.new("RGB", (400, 300), (30, 40, 50)).save(image_path)
    config = get_config()
    config["auto_save"] = False
    window = MainWindow(config=config, filename=str(image_path))
    qtbot.addWidget(window)
    window.resize(1200, 900)
    window.show()
    qtbot.waitUntil(lambda: not window.image.isNull())
    window.setClean()
    return window


def _polygon(label, x, y, width, height):
    return dict(
        label=label,
        group_id=None,
        points=[
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ],
        shape_type="polygon",
        mask=None,
        flags={},
        other_data={},
    )


def _add_defects(window):
    window.loadLabels(
        [
            _polygon("scratch", 20, 20, 8, 6),
            _polygon("scratch", 200, 120, 6, 5),
            _polygon("stain", 300, 200, 10, 8),
            _polygon("dent", 100, 250, 12, 9),
        ]
    )


@pytest.mark.gui
def test_inspector_groups_defects_by_category(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        _add_defects(window)
        dock = window.defect_inspector_dock
        dock.refresh()

        assert dock.category_combo.count() == 4  # 全部缺陷 + 3 类
        assert dock.category_combo.itemData(0) is None
        categories = {
            dock.category_combo.itemData(index)
            for index in range(1, dock.category_combo.count())
        }
        assert categories == {"scratch", "stain", "dent"}
        assert dock.defect_list.count() == 4
        assert "当前图片共 4 个缺陷" in dock.summary_label.text()

        scratch_index = dock.category_combo.findData("scratch")
        dock.category_combo.setCurrentIndex(scratch_index)
        assert len(dock._shapes) == 2
        assert dock.defect_list.count() == 2
        assert {shape.label for shape in dock._shapes} == {"scratch"}
        assert dock.show_only_checkbox.isEnabled() is True

        # 仅显示当前类别：其他类别的 labelList 勾选被去掉，画布可见性同步。
        states = {item.shape().label: item.checkState() for item in window.labelList}
        assert states["scratch"] == Qt.Checked
        assert states["stain"] == Qt.Unchecked
        assert states["dent"] == Qt.Unchecked

        # 切回“全部缺陷”后恢复显示，并自动取消只看当前类别。
        dock.category_combo.setCurrentIndex(0)
        assert dock.defect_list.count() == 4
        assert all(
            item.checkState() == Qt.Checked for item in window.labelList
        )
        assert dock.show_only_checkbox.isChecked() is False
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_show_only_uses_selected_defect_in_all_mode(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        _add_defects(window)
        dock = window.defect_inspector_dock
        dock.refresh()

        # “全部缺陷”不应把只看当前类别选项禁用。
        assert dock.show_only_checkbox.isEnabled() is True

        # 全部模式下未选中缺陷时勾选不影响显示（默认就是全部显示）。
        dock.show_only_checkbox.setChecked(True)
        assert all(
            item.checkState() == Qt.Checked for item in window.labelList
        )

        # 选中一条缺陷后，按该缺陷的类别过滤画布。
        dock._jump(0)
        states = {item.shape().label: item.checkState() for item in window.labelList}
        assert states["scratch"] == Qt.Checked
        assert states["stain"] == Qt.Unchecked
        assert states["dent"] == Qt.Unchecked

        # 切到另一类缺陷时，过滤类别跟随当前缺陷。
        stain_row = next(
            index
            for index, shape in enumerate(dock._shapes)
            if shape.label == "stain"
        )
        dock._jump(stain_row)
        states = {item.shape().label: item.checkState() for item in window.labelList}
        assert states["stain"] == Qt.Checked
        assert states["scratch"] == Qt.Unchecked
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_inspector_jumps_and_auto_zooms(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        _add_defects(window)
        dock = window.defect_inspector_dock
        dock.refresh()

        base_zoom = window.zoomWidget.value()
        scratch_index = dock.category_combo.findData("scratch")
        dock.category_combo.setCurrentIndex(scratch_index)
        # 选中类别后自动跳到该类别第一个缺陷并放大。
        assert window.canvas.selectedShapes == [dock._shapes[0]]
        assert window.zoomWidget.value() > base_zoom

        dock.step(1)
        shape = dock._shapes[1]
        assert window.canvas.selectedShapes == [shape]
        assert shape.selected is True

        # 小缺陷应当被放大到足够大，并且位于视口中心附近。
        assert window.zoomWidget.value() >= 2000
        rect = shape.boundingRect()
        canvas = window.canvas
        viewport = canvas.parentWidget()
        offset_center = canvas.offsetToCenter()
        h_value = window.scrollBars[Qt.Horizontal].value()
        v_value = window.scrollBars[Qt.Vertical].value()
        relative_center_x = (
            rect.center().x() + offset_center.x() + canvas.offset.x()
        ) * canvas.scale - h_value
        relative_center_y = (
            rect.center().y() + offset_center.y() + canvas.offset.y()
        ) * canvas.scale - v_value
        assert abs(relative_center_x - viewport.width() / 2) <= 2
        assert abs(relative_center_y - viewport.height() / 2) <= 2

        # 单图窗口：最后一个之后没有下一张，停在原图。
        dock._set_row(len(dock._shapes) - 1)
        filename_before = window.filename
        window.setClean()
        dock.step(1)
        assert window.filename == filename_before
        assert dock.defect_list.currentRow() == len(dock._shapes) - 1

        # 关闭自动放大时只选中，不改变缩放。
        dock.auto_zoom_checkbox.setChecked(False)
        zoom_before = window.zoomWidget.value()
        dock.step(1)
        assert window.zoomWidget.value() == zoom_before
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_inspector_empty_image(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        dock = window.defect_inspector_dock
        dock.refresh()
        assert dock.category_combo.count() == 1
        assert dock.defect_list.count() == 0
        assert dock.defect_list.isEnabled() is False
        assert dock.summary_label.text() == "当前图片暂无缺陷"
        assert dock.position_label.text() == "0/0"
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_inspector_category_persists_across_images(qtbot, tmp_path):

    window = _create_window(qtbot, tmp_path)
    try:
        _add_defects(window)
        dock = window.defect_inspector_dock
        dock.refresh()
        dock.category_combo.setCurrentIndex(dock.category_combo.findData("scratch"))
        assert dock._category == "scratch"

        # 模拟加载下一张图片：标注变化后仍保留类别筛选。
        window.labelList.clear()
        window.canvas.loadShapes([])
        window.loadLabels([_polygon("scratch", 30, 30, 7, 7)])
        dock.on_image_loaded()
        assert dock._category == "scratch"
        assert len(dock._shapes) == 1
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_inspector_has_previous_next_shortcuts(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        dock = window.defect_inspector_dock
        assert dock.prev_action.shortcut().toString() == "Alt+Left"
        assert dock.next_action.shortcut().toString() == "Alt+Right"
    finally:
        window.setClean()
        window.close()


def _point(label, x, y):
    return dict(
        label=label,
        group_id=None,
        points=[(x, y)],
        shape_type="point",
        mask=None,
        flags={},
        other_data={},
    )


@pytest.mark.gui
def test_inspector_zooms_point_shape(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        window.loadLabels(
            [_point("dust", 120, 90), _polygon("scratch", 200, 100, 8, 6)]
        )
        dock = window.defect_inspector_dock
        dock.refresh()
        dock.category_combo.setCurrentIndex(dock.category_combo.findData("dust"))

        assert window.zoomWidget.value() >= 2000
        assert [shape.label for shape in window.canvas.selectedShapes] == ["dust"]

        # 画布选中单个标注时，巡检列表跟随高亮。
        scratch = next(
            shape for shape in window.canvas.shapes if shape.label == "scratch"
        )
        window.canvas.selectShapes([scratch])
        assert dock.category_combo.currentData() == "dust"
        assert dock.defect_list.currentRow() == 0
        dock.category_combo.setCurrentIndex(0)
        window.canvas.selectShapes([scratch])
        assert dock.defect_list.currentRow() == 1
    finally:
        window.setClean()
        window.close()


def _json_shape(label, x, y, width, height):
    shape = _polygon(label, x, y, width, height)
    shape["description"] = ""
    shape["points"] = [list(point) for point in shape["points"]]
    return shape


def _create_dataset_window(qtbot, tmp_path, specs):
    directory = tmp_path / "dataset"
    directory.mkdir()
    paths = []
    for index, shapes in enumerate(specs, start=1):
        image_path = directory / f"image_{index:02d}.png"
        Image.new("RGB", (400, 300), (index * 20, 80, 160)).save(image_path)
        data = {
            "version": "5.0.1",
            "imagePath": image_path.name,
            "imageData": None,
            "imageWidth": 400,
            "imageHeight": 300,
            "shapes": shapes,
            "flags": {},
        }
        image_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        paths.append(image_path)

    config = get_config()
    config["auto_save"] = False
    window = MainWindow(config=config)
    qtbot.addWidget(window)
    window.resize(1200, 900)
    window.show()
    window.importDirImages(str(directory))
    window.fileListWidget.select_file_path(str(paths[0]))
    qtbot.waitUntil(lambda: window.filename is not None and not window.image.isNull())
    window.setClean()
    return window, paths


def _dataset_specs():
    return [
        [
            _json_shape("scratch", 20, 20, 8, 6),
            _json_shape("scratch", 120, 100, 7, 5),
            _json_shape("stain", 200, 150, 10, 8),
        ],
        [
            _json_shape("stain", 50, 50, 12, 9),
        ],
        [
            _json_shape("scratch", 60, 60, 9, 6),
            _json_shape("dent", 250, 200, 11, 9),
        ],
    ]


@pytest.mark.gui
def test_inspector_moves_to_next_and_previous_image(qtbot, tmp_path):
    window, paths = _create_dataset_window(qtbot, tmp_path, _dataset_specs())
    try:
        dock = window.defect_inspector_dock
        dock.refresh()
        assert dock.defect_list.count() == 3

        # 最后一个缺陷之后 → 下一张图片，并定位第一个缺陷。
        dock._set_row(2)
        window.setClean()
        dock.step(1)
        assert Path(window.filename).name == paths[1].name
        assert dock.defect_list.count() == 1
        assert dock.defect_list.currentRow() == 0
        assert [shape.label for shape in window.canvas.selectedShapes] == ["stain"]

        # 再按一次 → 第三张图片。
        window.setClean()
        dock.step(1)
        assert Path(window.filename).name == paths[2].name
        assert dock.defect_list.currentRow() == 0

        # 第一个缺陷之前 → 上一张图片，并定位最后一个缺陷。
        window.setClean()
        dock.step(-1)
        assert Path(window.filename).name == paths[1].name
        assert dock.defect_list.currentRow() == dock.defect_list.count() - 1
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_inspector_stops_at_dataset_edges(qtbot, tmp_path):
    window, paths = _create_dataset_window(qtbot, tmp_path, _dataset_specs())
    try:
        dock = window.defect_inspector_dock
        dock.refresh()
        dock._set_row(0)
        window.setClean()
        dock.step(-1)
        assert Path(window.filename).name == paths[0].name

        window.setClean()
        window.fileListWidget.select_file_path(str(paths[2]))
        qtbot.waitUntil(lambda: Path(window.filename).name == paths[2].name)
        window.setClean()
        dock.refresh()
        dock._set_row(dock.defect_list.count() - 1)
        window.setClean()
        dock.step(1)
        assert Path(window.filename).name == paths[2].name
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_inspector_category_navigation_crosses_images(qtbot, tmp_path):
    window, paths = _create_dataset_window(qtbot, tmp_path, _dataset_specs())
    try:
        dock = window.defect_inspector_dock
        dock.refresh()
        dock.category_combo.setCurrentIndex(dock.category_combo.findData("scratch"))
        assert [shape.label for shape in dock._shapes] == ["scratch", "scratch"]

        window.setClean()
        dock.step(1)
        assert dock.defect_list.currentRow() == 1

        # 第二张没有 scratch：仍然跳到第二张，保留类别筛选。
        window.setClean()
        dock.step(1)
        assert Path(window.filename).name == paths[1].name
        assert dock._category == "scratch"
        assert dock.category_combo.currentData() == "scratch"
        assert dock.category_combo.currentText() == "scratch (0)"
        assert dock.defect_list.count() == 0
        assert "没有" in dock.summary_label.text()
        assert "scratch" in dock.summary_label.text()

        # 当前类别在本图没有缺陷时，左右按钮仍可点击换图。
        assert dock.prev_btn.isEnabled() is True
        assert dock.next_btn.isEnabled() is True
        window.setClean()
        dock.next_btn.click()
        assert Path(window.filename).name == paths[2].name
        assert dock.defect_list.count() == 1
        assert dock.defect_list.currentRow() == 0
        assert [shape.label for shape in window.canvas.selectedShapes] == ["scratch"]

        # 反向跨越时同样保留类别。
        window.setClean()
        dock.step(-1)
        assert Path(window.filename).name == paths[1].name
        assert dock._category == "scratch"
        assert dock.defect_list.count() == 0
    finally:
        window.setClean()
        window.close()
