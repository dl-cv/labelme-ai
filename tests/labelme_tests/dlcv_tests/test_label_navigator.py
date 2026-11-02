"""多边形标签上方的缺陷导航条：类别筛选、跨图切换与自动放大。"""

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


def _add_defects(window):
    window.loadLabels(
        [
            _polygon("scratch", 20, 20, 8, 6),
            _polygon("scratch", 200, 120, 6, 5),
            _polygon("stain", 300, 200, 10, 8),
            _polygon("dent", 100, 250, 12, 9),
        ]
    )


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
def test_navigator_is_merged_into_polygon_labels(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        assert not hasattr(window, "defect_inspector_dock")
        assert window.label_navigator.parent() is window.shape_dock.widget()
        assert window.labelList.parent() is window.shape_dock.widget()
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_filters_label_list_rows(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        _add_defects(window)
        navigator = window.label_navigator
        navigator.refresh()

        assert navigator.category_combo.count() == 4  # 全部缺陷 + 3 类
        assert navigator.category_combo.itemData(0) is None
        assert len(window.labelList) == 4
        assert all(
            not window.labelList.isRowHidden(row) for row in range(4)
        )

        navigator.category_combo.setCurrentIndex(
            navigator.category_combo.findData("scratch")
        )
        assert navigator._category == "scratch"
        assert [item.shape().label for item in navigator._visible_items()] == [
            "scratch",
            "scratch",
        ]
        labels = [item.shape().label for item in window.labelList]
        for row, label in enumerate(labels):
            assert window.labelList.isRowHidden(row) == (label != "scratch")

        # 选中具体类别时，画布同步只显示该类。
        states = {
            item.shape().label: item.checkState() for item in window.labelList
        }
        assert states["scratch"] == Qt.Checked
        assert states["stain"] == Qt.Unchecked
        assert states["dent"] == Qt.Unchecked

        # 全部缺陷：恢复所有行和勾选。
        navigator.category_combo.setCurrentIndex(0)
        assert all(
            not window.labelList.isRowHidden(row) for row in range(4)
        )
        assert all(
            item.checkState() == Qt.Checked for item in window.labelList
        )
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_zooms_and_stepping(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        _add_defects(window)
        navigator = window.label_navigator
        navigator.refresh()
        navigator.category_combo.setCurrentIndex(
            navigator.category_combo.findData("scratch")
        )
        visible = navigator._visible_items()
        assert window.canvas.selectedShapes == [visible[0].shape()]
        assert window.zoomWidget.value() >= 2000

        navigator.step(1)
        visible = navigator._visible_items()
        assert window.canvas.selectedShapes == [visible[1].shape()]
        assert navigator.position_label.text() == "2/2"

        shape = visible[1].shape()
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

        # 关闭自动放大后只选中，不改变缩放。
        navigator.auto_zoom_checkbox.setChecked(False)
        zoom_before = window.zoomWidget.value()
        navigator._jump_to_item(visible[0])
        assert window.canvas.selectedShapes == [visible[0].shape()]
        assert window.zoomWidget.value() == zoom_before
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_point_shape(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        window.loadLabels(
            [_point("dust", 120, 90), _polygon("scratch", 200, 100, 8, 6)]
        )
        navigator = window.label_navigator
        navigator.refresh()
        navigator.category_combo.setCurrentIndex(
            navigator.category_combo.findData("dust")
        )
        assert window.zoomWidget.value() >= 2000
        assert [shape.label for shape in window.canvas.selectedShapes] == ["dust"]
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_moves_to_next_and_previous_image(qtbot, tmp_path):
    window, paths = _create_dataset_window(qtbot, tmp_path, _dataset_specs())
    try:
        navigator = window.label_navigator
        navigator.refresh()
        visible = navigator._visible_items()
        assert len(visible) == 3
        assert navigator.prev_btn.isEnabled() is True
        assert navigator.next_btn.isEnabled() is True

        navigator._jump_to_item(visible[-1])
        window.setClean()
        navigator.step(1)
        assert Path(window.filename).name == paths[1].name
        assert len(navigator._visible_items()) == 1
        assert navigator.position_label.text() == "1/1"

        window.setClean()
        navigator.step(1)
        assert Path(window.filename).name == paths[2].name
        assert navigator.position_label.text() == "1/2"

        window.setClean()
        navigator.step(-1)
        assert Path(window.filename).name == paths[1].name
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_stops_at_dataset_edges(qtbot, tmp_path):
    window, paths = _create_dataset_window(qtbot, tmp_path, _dataset_specs())
    try:
        navigator = window.label_navigator
        navigator.refresh()
        navigator._jump_to_item(navigator._visible_items()[0])
        window.setClean()
        navigator.step(-1)
        assert Path(window.filename).name == paths[0].name

        window.setClean()
        window.fileListWidget.select_file_path(str(paths[2]))
        qtbot.waitUntil(lambda: Path(window.filename).name == paths[2].name)
        window.setClean()
        navigator.refresh()
        navigator._jump_to_item(navigator._visible_items()[-1])
        window.setClean()
        navigator.step(1)
        assert Path(window.filename).name == paths[2].name
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_category_crosses_images(qtbot, tmp_path):
    window, paths = _create_dataset_window(qtbot, tmp_path, _dataset_specs())
    try:
        navigator = window.label_navigator
        navigator.refresh()
        navigator.category_combo.setCurrentIndex(
            navigator.category_combo.findData("scratch")
        )
        assert [item.shape().label for item in navigator._visible_items()] == [
            "scratch",
            "scratch",
        ]

        window.setClean()
        navigator.step(1)
        window.setClean()
        navigator.step(1)
        assert Path(window.filename).name == paths[1].name
        assert navigator._category == "scratch"
        assert navigator.category_combo.currentText() == "scratch (0)"
        assert navigator._visible_items() == []
        assert navigator.prev_btn.isEnabled() is True
        assert navigator.next_btn.isEnabled() is True

        # 当前类别没有缺陷时，左右按钮仍能换图。
        window.setClean()
        navigator.next_btn.click()
        assert Path(window.filename).name == paths[2].name
        assert len(navigator._visible_items()) == 1
        assert navigator.position_label.text() == "1/1"

        window.setClean()
        navigator.step(-1)
        assert Path(window.filename).name == paths[1].name
        assert navigator._category == "scratch"
        assert navigator._visible_items() == []
    finally:
        window.setClean()
        window.close()


@pytest.mark.gui
def test_navigator_empty_image(qtbot, tmp_path):
    window = _create_window(qtbot, tmp_path)
    try:
        navigator = window.label_navigator
        navigator.refresh()
        assert navigator.category_combo.count() == 1
        assert navigator._visible_items() == []
        assert navigator.position_label.text() == "0/0"
    finally:
        window.setClean()
        window.close()
