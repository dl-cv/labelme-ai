"""图像筛选：按标注类别过滤文件树（截图样式筛选项 + 后台统计）。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from qtpy import QtCore
from qtpy import QtWidgets

from labelme.dlcv.file_tree_widget import FileTreeWidget
from labelme.dlcv.store import STORE
from labelme.dlcv.widget.file_tree_filter import FileTreeFilter
from labelme.dlcv.widget.image_filter_panel import ImageFilterIndex
from labelme.dlcv.widget.image_filter_panel import image_key


def _write_json(path: Path, labels):
    path.write_text(
        json.dumps(
            {
                "imagePath": path.with_suffix(".png").name,
                "shapes": [{"label": label} for label in labels],
                "flags": {},
            }
        ),
        encoding="utf-8",
    )


def _image_paths(root: Path, names):
    for name in names:
        path = root / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not-a-real-image")
    return [root / f"{name}.png" for name in names]


def _build_dataset(root: Path):
    """cat: a,b；dog: b,sub/c；未标注: sub/d、e（空 shapes）、broken（坏 JSON）。"""
    _image_paths(root, ["a", "b", "e", "broken", "sub/c", "sub/d"])
    (root / "label.txt").write_text("cat\ndog\n类别 1\n", encoding="utf-8")
    _write_json(root / "a.json", ["cat"])
    _write_json(root / "b.json", ["cat", "dog"])
    _write_json(root / "e.json", [])
    (root / "broken.json").write_text("{not json", encoding="utf-8")
    _write_json(root / "sub" / "c.json", ["dog"])


def _bulk_dataset(root: Path, count: int = 120):
    root.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        image = root / f"img_{index:03d}.png"
        image.write_bytes(b"not-a-real-image")
        _write_json(image.with_suffix(".json"), ["cat" if index % 2 else "dog"])


def _get_json_path(image_path):
    return str(Path(image_path).with_suffix(".json"))


def _items_by_path(tree):
    items = {}
    iterator = QtWidgets.QTreeWidgetItemIterator(tree)
    while iterator.value():
        item = iterator.value()
        path = item.data(0, QtCore.Qt.UserRole)
        if path:
            items[path] = item
        iterator += 1
    return items


def _visible_files(panel):
    tree = panel.tree_widget
    visible = set()
    for path, item in _items_by_path(tree).items():
        if path in tree._file_items and not item.isHidden():
            visible.add(path)
    return visible


def _expand_folder(panel, name):
    tree = panel.tree_widget
    root = tree.invisibleRootItem()
    for index in range(root.childCount()):
        item = root.child(index)
        if item.super_text(0) == name:
            item.setExpanded(True)
            return item
    raise KeyError(name)


@pytest.fixture
def file_tree(qapp):
    try:
        previous = STORE.main_window
    except AssertionError:
        previous = None
    STORE.register_main_window(
        SimpleNamespace(
            proj_manager=SimpleNamespace(get_json_path=_get_json_path),
        )
    )
    panel = FileTreeWidget()
    panel.resize(420, 720)
    try:
        yield panel
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
        STORE.register_main_window(previous)


# ------------------------- 纯数据：扫描索引 -------------------------


def test_file_tree_filter_combines_conditions_lazily():
    calls = []

    def is_annotated(path):
        calls.append(path)
        return path.endswith("a.png")

    annotated_only = FileTreeFilter(search_text="x/", show_annotated=True)
    assert annotated_only.matches("x/a.png", is_annotated) is True
    assert annotated_only.matches("x/b.png", is_annotated) is False
    assert calls == ["x/a.png", "x/b.png"]

    # 不启用标注状态过滤时，不应该读取 JSON/标注信息。
    calls.clear()
    text_only = FileTreeFilter(search_text="x/")
    assert text_only.matches("x/c.png", is_annotated) is True
    assert calls == []


def test_file_tree_filter_category_conditions(tmp_path):
    _build_dataset(tmp_path)
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))

    cat_filter = FileTreeFilter(
        categories=frozenset({"cat"}), index=index
    )
    assert cat_filter.matches(tmp_path / "a.png", lambda _path: True)
    assert cat_filter.matches(tmp_path / "sub" / "c.png", lambda _path: True) is False
    assert cat_filter.matches(tmp_path / "sub" / "d.png", lambda _path: True) is False


def test_annotated_filter_scans_each_directory_once(
    file_tree, tmp_path, monkeypatch
):
    import labelme.dlcv.file_tree_widget as tree_module

    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    real_scandir = tree_module.os.scandir
    scanned = []

    def counting_scandir(path):
        scanned.append(str(path))
        return real_scandir(path)

    monkeypatch.setattr(tree_module.os, "scandir", counting_scandir)
    file_tree.show_annotated_checkbox.setChecked(True)

    # 根目录 4 张图片共享一次 scandir 结果，而不是每张图 stat 一次。
    assert len(scanned) == 1


def test_filter_component_owns_its_stylesheet(file_tree):
    # 卡片和入口按钮使用组件内局部样式，原版 UI 下也不依赖全局 modern QSS。
    assert "imageFilterPanel" in file_tree.image_filter.styleSheet()
    assert "imageFilterApply" in file_tree.image_filter.styleSheet()
    assert "fileFilterBtn" in file_tree.image_filter_btn.styleSheet()


def test_tree_filter_component_applies_and_resets(qapp):
    from qtpy import QtCore as QtCoreAlias
    from qtpy import QtWidgets as QtWidgetsAlias

    from labelme.dlcv.widget.file_tree_filter import FileTreeFilter
    from labelme.dlcv.widget.file_tree_filter import TreeFilter

    tree = QtWidgetsAlias.QTreeWidget()
    root = tree.invisibleRootItem()
    folder = QtWidgetsAlias.QTreeWidgetItem(root)
    folder.setText(0, "sub")
    folder.setData(0, QtCoreAlias.Qt.UserRole, "C:/root/sub")
    image = QtWidgetsAlias.QTreeWidgetItem(folder)
    image.setText(0, "a.png")
    image.setData(0, QtCoreAlias.Qt.UserRole, "C:/root/sub/a.png")
    file_items = {"C:/root/sub/a.png": image}
    tree_filter = TreeFilter(tree, lambda: file_items, path_key=lambda p: p)

    tree_filter.apply(FileTreeFilter(search_text="zzz"))
    assert image.isHidden() is True
    assert folder.isHidden() is True

    tree_filter.apply(FileTreeFilter(search_text="a.png"))
    assert image.isHidden() is False
    assert folder.isHidden() is False

    tree_filter.apply(FileTreeFilter(search_text="zzz"))
    tree_filter.reset()
    assert image.isHidden() is False
    assert folder.isHidden() is False


def test_filename_search_hides_folders_without_matches(file_tree, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    sub_item = _expand_folder(file_tree, "sub")

    file_tree.search_box.setText("a.png")
    file_tree.search_box.returnPressed.emit()

    assert sub_item.isHidden() is True
    assert _visible_files(file_tree) == {(tmp_path / "a.png").as_posix()}

    file_tree.search_box.clear()
    assert sub_item.isHidden() is False
    assert len(_visible_files(file_tree)) == 6


def test_filename_search_applies_on_enter_or_other_filter_action(
    file_tree, tmp_path
):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    _expand_folder(file_tree, "sub")

    file_tree.search_box.setText("broken")
    # 只输入不回车：不筛选。
    assert len(_visible_files(file_tree)) == 6

    # 切换其他过滤条件时，会连同搜索框里已输入的内容一起应用。
    file_tree.show_annotated_checkbox.setChecked(True)
    assert _visible_files(file_tree) == {(tmp_path / "broken.png").as_posix()}
    file_tree.show_annotated_checkbox.setChecked(False)

    file_tree.search_box.returnPressed.emit()
    assert _visible_files(file_tree) == {(tmp_path / "broken.png").as_posix()}

    file_tree.search_box.clear()
    assert len(_visible_files(file_tree)) == 6


def test_index_counts_images_per_category_and_unannotated(tmp_path):
    _build_dataset(tmp_path)

    index = ImageFilterIndex.build(
        tmp_path, _get_json_path, (".png",), ["cat", "dog", "类别 1"]
    )

    assert index is not None
    assert list(index.categories) == ["cat", "dog", "类别 1"]
    assert index.categories["cat"] == 2
    assert index.categories["dog"] == 2
    assert index.categories["类别 1"] == 0
    assert index.total_images == 6
    assert index.unannotated_count == 3
    assert index.failed_count == 1
    assert index.dir_error_count == 0

    assert index.labels_for(tmp_path / "b.png") == frozenset({"cat", "dog"})
    assert index.labels_for(tmp_path / "sub" / "c.png") == frozenset({"dog"})
    assert index.labels_for(tmp_path / "sub" / "d.png") == frozenset()
    assert index.labels_for(tmp_path / "missing.png") is None
    assert index.matched_directories({"dog"}) == {
        image_key(tmp_path / "sub")
    }
    assert index.matched_directories({"cat"}) == set()


def test_index_extra_categories_sorted_by_count(tmp_path):
    _image_paths(tmp_path, ["1", "2", "3"])
    _write_json(tmp_path / "1.json", ["rare", "common"])
    _write_json(tmp_path / "2.json", ["common"])
    _write_json(tmp_path / "3.json", ["common"])

    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))

    assert list(index.categories) == ["common", "rare"]
    assert index.categories == {"common": 3, "rare": 1}
    assert index.unannotated_count == 0


def test_index_reports_progress_and_can_be_cancelled(tmp_path):
    _build_dataset(tmp_path)
    progress = []

    index = ImageFilterIndex.build(
        tmp_path, _get_json_path, (".png",), progress=progress.append
    )
    assert index is not None
    assert progress == list(range(1, 7))

    cancelled = ImageFilterIndex.build(
        tmp_path, _get_json_path, (".png",), cancel_check=lambda: True
    )
    assert cancelled is None


# ------------------------- 文件树联动 -------------------------


def test_apply_and_cancel_category_filter(file_tree, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    _expand_folder(file_tree, "sub")
    file_tree.image_filter._index = ImageFilterIndex.build(
        tmp_path, _get_json_path, (".png",), ["cat", "dog", "类别 1"]
    )
    file_tree.image_filter._dirty = False
    file_tree.image_filter._selected = {"cat"}
    file_tree._apply_filters()

    visible = _visible_files(file_tree)
    assert visible == {
        (tmp_path / "a.png").as_posix(),
        (tmp_path / "b.png").as_posix(),
    }
    items = _items_by_path(file_tree.tree_widget)
    assert items[(tmp_path / "sub").as_posix()].isHidden() is True

    file_tree.image_filter.cancel_filters()
    assert file_tree.image_filter._selected == set()
    assert len(_visible_files(file_tree)) == 6
    assert not _items_by_path(file_tree.tree_widget)[
        (tmp_path / "sub").as_posix()
    ].isHidden()


def test_category_filter_combines_with_annotation_checkbox(file_tree, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    _expand_folder(file_tree, "sub")
    file_tree.image_filter._index = ImageFilterIndex.build(
        tmp_path, _get_json_path, (".png",)
    )
    file_tree.image_filter._selected = {"dog"}
    file_tree.show_annotated_checkbox.setChecked(True)

    visible = _visible_files(file_tree)
    assert visible == {
        (tmp_path / "b.png").as_posix(),
        (tmp_path / "sub" / "c.png").as_posix(),
    }


def test_lazy_loaded_children_follow_active_filter(file_tree, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    file_tree.image_filter._index = ImageFilterIndex.build(
        tmp_path, _get_json_path, (".png",)
    )
    file_tree.image_filter._selected = {"cat"}
    file_tree._apply_filters()

    _expand_folder(file_tree, "sub")
    files = _visible_files(file_tree)
    assert (tmp_path / "sub" / "c.png").as_posix() not in files
    assert (tmp_path / "sub" / "d.png").as_posix() not in files


def test_panel_scan_and_apply_flow(file_tree, qtbot, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    _expand_folder(file_tree, "sub")
    file_tree.show()

    file_tree.image_filter_btn.click()
    panel = file_tree.image_filter
    assert file_tree._body_stack.currentWidget() is panel
    qtbot.waitUntil(lambda: not panel.is_loading(), timeout=10000)

    assert set(panel.category_rows) == {"cat", "dog", "类别 1"}
    assert panel.category_rows["cat"].count == 2
    assert panel.category_rows["类别 1"].count == 0
    # 筛选卡片只展示真实类别，不再提供“未标注”这一行。
    assert not hasattr(panel, "unannotated_row")
    assert panel.apply_btn.isEnabled()

    panel.category_rows["cat"].set_checked(True)
    panel.apply_btn.click()

    assert file_tree._body_stack.currentWidget() is file_tree.tree_widget
    assert file_tree.image_filter._selected == {"cat"}
    assert file_tree.image_filter_btn.property("active") is True
    assert _visible_files(file_tree) == {
        (tmp_path / "a.png").as_posix(),
        (tmp_path / "b.png").as_posix(),
    }

    # 重新打开时恢复已应用的勾选状态，取消后恢复全部图片。
    file_tree.image_filter_btn.click()
    assert file_tree.image_filter.category_rows["cat"].is_checked() is True
    file_tree.image_filter.cancel_btn.click()
    assert file_tree.image_filter._selected == set()
    assert len(_visible_files(file_tree)) == 6
    assert file_tree.image_filter_btn.property("active") is False


def test_refresh_keeps_category_filter(file_tree, qtbot, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))
    file_tree.image_filter._index = index
    file_tree.image_filter._selected = {"cat"}
    file_tree._apply_filters()

    file_tree.refresh_directory()
    qtbot.waitUntil(lambda: file_tree.image_filter._scan_thread is None, timeout=10000)

    assert file_tree.image_filter._selected == {"cat"}
    assert file_tree.image_filter._dirty is False
    assert _visible_files(file_tree) == {
        (tmp_path / "a.png").as_posix(),
        (tmp_path / "b.png").as_posix(),
    }


def test_apply_after_stale_scan_rescans_before_filtering(
    file_tree, qtbot, tmp_path
):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))
    file_tree.image_filter._index = index

    file_tree.image_filter_btn.click()
    panel = file_tree.image_filter
    qtbot.waitUntil(lambda: panel.is_ready(), timeout=10000)
    # 模拟面板打开期间保存过标注：扫描结果过期，应用筛选前必须重扫。
    file_tree.image_filter._dirty = True
    panel.category_rows["cat"].set_checked(True)
    panel.apply_btn.click()

    assert panel.is_loading() is True
    qtbot.waitUntil(lambda: file_tree.image_filter._scan_thread is None, timeout=10000)
    qtbot.waitUntil(
        lambda: file_tree._body_stack.currentWidget() is file_tree.tree_widget,
        timeout=5000,
    )
    assert file_tree.image_filter._selected == {"cat"}
    assert _visible_files(file_tree) == {
        (tmp_path / "a.png").as_posix(),
        (tmp_path / "b.png").as_posix(),
    }


def test_clicking_category_row_toggles_check(file_tree, qtbot, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    file_tree.image_filter_btn.click()
    panel = file_tree.image_filter
    qtbot.waitUntil(lambda: panel.is_ready(), timeout=10000)

    row = panel.category_rows["cat"]
    qtbot.mouseClick(row, QtCore.Qt.LeftButton)
    assert row.is_checked() is True
    qtbot.mouseClick(row.check_btn, QtCore.Qt.LeftButton)
    assert row.is_checked() is False


def test_close_button_keeps_applied_filter(file_tree, qtbot, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))
    file_tree.image_filter._index = index
    file_tree.image_filter._selected = {"cat"}
    file_tree._apply_filters()

    file_tree.image_filter_btn.click()
    qtbot.waitUntil(lambda: file_tree.image_filter.is_ready(), timeout=10000)
    file_tree.image_filter.close_btn.click()

    assert file_tree._body_stack.currentWidget() is file_tree.tree_widget
    assert file_tree.image_filter._selected == {"cat"}
    assert len(_visible_files(file_tree)) == 2


def test_root_change_resets_category_filter(file_tree, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))
    file_tree.image_filter._index = index
    file_tree.image_filter._selected = {"cat"}
    file_tree._apply_filters()

    other = tmp_path / "other"
    _image_paths(other, ["x"])
    file_tree.set_root_dir(str(other))

    assert file_tree.image_filter._selected == set()
    assert file_tree.image_filter._index is None
    assert file_tree.image_filter_btn.property("active") is False
    assert file_tree._body_stack.currentWidget() is file_tree.tree_widget
    assert _visible_files(file_tree) == {(other / "x.png").as_posix()}


def test_scan_without_open_folder_shows_message(file_tree):
    file_tree.image_filter_btn.click()
    assert file_tree.image_filter.is_ready() is False
    assert "打开" in file_tree.image_filter.status_label.text()


def test_close_while_scanning_stops_thread(file_tree, tmp_path):
    _bulk_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    file_tree.image_filter_btn.click()

    file_tree.close()

    assert file_tree.image_filter._scan_thread is None


def test_root_change_while_scanning_resets_filter(file_tree, tmp_path):
    _bulk_dataset(tmp_path / "first")
    _bulk_dataset(tmp_path / "second", count=3)
    file_tree.set_root_dir(str(tmp_path / "first"))
    file_tree.image_filter_btn.click()

    file_tree.set_root_dir(str(tmp_path / "second"))

    assert file_tree.image_filter._scan_thread is None
    assert file_tree.image_filter._index is None
    assert file_tree._body_stack.currentWidget() is file_tree.tree_widget
    assert len(file_tree.image_list) == 3


def test_reopening_panel_without_changes_does_not_rescan(
    file_tree, qtbot, tmp_path
):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    file_tree.image_filter_btn.click()
    panel = file_tree.image_filter
    qtbot.waitUntil(lambda: panel.is_ready(), timeout=10000)
    generation = file_tree.image_filter._generation

    panel.close_btn.click()
    file_tree.image_filter_btn.click()
    qtbot.waitUntil(lambda: panel.is_ready(), timeout=10000)

    assert file_tree.image_filter._generation == generation
    assert file_tree.image_filter._dirty is False


def test_expanding_folders_does_not_mark_scan_dirty(file_tree, tmp_path):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    assert file_tree.image_filter._dirty is False

    _expand_folder(file_tree, "sub")

    assert file_tree.image_filter._dirty is False


def test_pruned_category_selection_restores_all_files(
    file_tree, qtbot, tmp_path
):
    # 不使用 label.txt，类别只来自 JSON：标注被删光后类别会从列表里消失。
    _image_paths(tmp_path, ["a", "b"])
    _write_json(tmp_path / "a.json", ["rare"])
    file_tree.set_root_dir(str(tmp_path))
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))
    file_tree.image_filter._index = index
    file_tree.image_filter._selected = {"rare"}
    file_tree._apply_filters()
    assert _visible_files(file_tree) == {(tmp_path / "a.png").as_posix()}

    # 模拟 rare 标注全部被删除，再次扫描后选中类别被剪空。
    (tmp_path / "a.json").unlink()
    file_tree.mark_category_dirty()
    file_tree.refresh_directory()
    qtbot.waitUntil(lambda: file_tree.image_filter._scan_thread is None, timeout=10000)

    assert file_tree.image_filter._selected == set()
    assert file_tree.image_filter._dirty is False
    assert file_tree.image_filter_btn.property("active") is False
    assert _visible_files(file_tree) == {
        (tmp_path / "a.png").as_posix(),
        (tmp_path / "b.png").as_posix(),
    }


def test_scan_result_stays_dirty_if_data_changed_while_scanning(
    file_tree, tmp_path
):
    _build_dataset(tmp_path)
    file_tree.set_root_dir(str(tmp_path))
    index = ImageFilterIndex.build(tmp_path, _get_json_path, (".png",))

    file_tree.image_filter._generation = 7
    file_tree.image_filter._data_epoch = 5
    file_tree.image_filter._on_scan_finished(7, 4, index)

    assert file_tree.image_filter._index is index
    assert file_tree.image_filter._dirty is True


@pytest.mark.gui
def test_saving_annotation_marks_scan_dirty(qtbot, tmp_path):
    from PIL import Image

    from labelme.config import get_config
    from labelme.dlcv.app import MainWindow

    directory = tmp_path / "dataset"
    directory.mkdir()
    image_path = directory / "a.png"
    Image.new("RGB", (60, 40), "white").save(image_path)

    config = get_config()
    config["auto_save"] = False
    window = MainWindow(config=config)
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    window.importDirImages(str(directory))
    window.fileListWidget.select_file_path(str(image_path))
    qtbot.waitUntil(
        lambda: window.filename is not None and not window.image.isNull(),
        timeout=10000,
    )
    window.setClean()
    tree = window.fileListWidget
    assert tree.image_filter._dirty is False

    window.loadLabels(
        [
            dict(
                label="cat",
                group_id=None,
                points=[(1, 1), (20, 1), (20, 20), (1, 20)],
                shape_type="polygon",
                mask=None,
                flags={},
                other_data={},
            )
        ]
    )
    window.setDirty()

    assert window.saveLabels(str(image_path.with_suffix(".json"))) is True

    assert tree.image_filter._dirty is True
    window.setClean()
    window.close()
