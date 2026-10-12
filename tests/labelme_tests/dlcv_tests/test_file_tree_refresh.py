import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from qtpy import QtCore, QtWidgets

from labelme.dlcv.file_tree_widget import FileTreeWidget
from labelme.dlcv.store import STORE


@pytest.fixture
def file_tree(qapp):
    try:
        previous = STORE.main_window
    except AssertionError:
        previous = None
    STORE.register_main_window(SimpleNamespace(proj_manager=SimpleNamespace(
        get_json_path=lambda path: str(Path(path).with_suffix(".json")),
    )))
    panel = FileTreeWidget()
    try:
        yield panel
    finally:
        panel.close()
        panel.deleteLater()
        qapp.processEvents()
        STORE.register_main_window(previous)


def write_image(path, annotated=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 16), "white").save(path)
    if annotated:
        path.with_suffix(".json").write_text(json.dumps({
            "imagePath": path.name, "shapes": [], "flags": {},
        }), encoding="utf-8")


def items_by_path(tree):
    items = {}
    iterator = QtWidgets.QTreeWidgetItemIterator(tree)
    while iterator.value():
        item = iterator.value()
        path = item.data(0, QtCore.Qt.UserRole)
        if path:
            items[path] = item
        iterator += 1
    return items


def test_refresh_adds_and_removes_root_entries_without_loading_new_folders(
    file_tree, tmp_path,
):
    removed_image = tmp_path / "removed.png"
    removed_folder = tmp_path / "removed-folder"
    write_image(removed_image)
    write_image(removed_folder / "old.png")
    file_tree.set_root_dir(str(tmp_path))
    items_by_path(file_tree.tree_widget)[removed_folder.as_posix()].setExpanded(True)

    removed_image.unlink()
    shutil.rmtree(removed_folder)
    new_folder = tmp_path / "new-folder"
    nested_image = new_folder / "nested.png"
    write_image(nested_image)
    root_images = [tmp_path / "image2.png", tmp_path / "image10.png"]
    for image in root_images:
        write_image(image)

    file_tree.refresh_directory()
    items = items_by_path(file_tree.tree_widget)
    assert set(items) == {new_folder.as_posix()} | {image.as_posix() for image in root_images}
    assert list(file_tree.image_list) == [image.as_posix() for image in root_images]
    assert not items[new_folder.as_posix()].isExpanded()

    items[new_folder.as_posix()].setExpanded(True)
    assert nested_image.as_posix() in items_by_path(file_tree.tree_widget)
    assert file_tree.count() == 3


def test_refresh_rescans_loaded_descendants_and_preserves_expansion(file_tree, tmp_path):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    open_folder = tmp_path / "open-folder"
    untouched = tmp_path / "untouched"
    write_image(inner / "old.png")
    write_image(open_folder / "old.png")
    write_image(untouched / "lazy.png")
    file_tree.set_root_dir(str(tmp_path))
    items = items_by_path(file_tree.tree_widget)
    items[outer.as_posix()].setExpanded(True)
    items = items_by_path(file_tree.tree_widget)
    items[inner.as_posix()].setExpanded(True)
    items[open_folder.as_posix()].setExpanded(True)
    items[outer.as_posix()].setExpanded(False)

    added_images = [inner / "new.png", open_folder / "new.png"]
    for image in added_images:
        write_image(image)
    unopened = outer / "unopened"
    write_image(unopened / "lazy.png")

    file_tree.refresh_directory()
    items = items_by_path(file_tree.tree_widget)
    assert not items[outer.as_posix()].isExpanded()
    assert items[inner.as_posix()].isExpanded()
    assert items[open_folder.as_posix()].isExpanded()
    assert all(image.as_posix() in items for image in added_images)
    assert unopened.as_posix() in items
    assert (unopened / "lazy.png").as_posix() not in items
    assert not items[untouched.as_posix()].isExpanded()
    assert (untouched / "lazy.png").as_posix() not in items


def test_refresh_preserves_current_and_multiple_selection_without_signals(file_tree, tmp_path):
    images = [tmp_path / "first.png", tmp_path / "second.png"]
    for image in images:
        write_image(image)
    file_tree.set_root_dir(str(tmp_path))
    tree = file_tree.tree_widget
    tree.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
    items = items_by_path(tree)
    tree.setCurrentItem(items[images[0].as_posix()])
    items[images[1].as_posix()].setSelected(True)
    selected_before = {item.get_path() for item in tree.selectedItems()}
    assert selected_before == {image.as_posix() for image in images}
    selection_changes = []
    current_changes = []
    file_selections = []
    tree.itemSelectionChanged.connect(lambda: selection_changes.append(True))
    tree.currentItemChanged.connect(lambda current, previous: current_changes.append(current))
    tree.sig_file_selected.connect(file_selections.append)
    write_image(tmp_path / "added.png")

    file_tree.refresh_directory()

    assert tree.currentItem().get_path() == images[0].as_posix()
    assert {item.get_path() for item in tree.selectedItems()} == selected_before
    assert not selection_changes
    assert not current_changes
    assert not file_selections


@pytest.mark.parametrize("show_annotated", [True, False])
def test_refresh_keeps_search_and_annotation_filters(file_tree, tmp_path, show_annotated):
    old = tmp_path / "keep-old.png"
    write_image(old, annotated=True)
    file_tree.set_root_dir(str(tmp_path))
    file_tree.search_box.setText("keep-")
    file_tree.search_box.returnPressed.emit()
    file_tree.show_annotated_checkbox.setChecked(show_annotated)
    file_tree.show_unannotated_checkbox.setChecked(not show_annotated)
    new = tmp_path / "keep-new.png"
    plain = tmp_path / "keep-plain.png"
    excluded = tmp_path / "excluded.png"
    write_image(new, annotated=True)
    write_image(plain)
    write_image(excluded, annotated=True)
    old.with_suffix(".json").unlink()

    file_tree.refresh_directory()

    items = items_by_path(file_tree.tree_widget)
    visible = {path for path, item in items.items() if not item.isHidden()}
    expected = {new.as_posix()} if show_annotated else {old.as_posix(), plain.as_posix()}
    assert visible == expected
    assert file_tree.search_box.text() == "keep-"
    assert file_tree.show_annotated_checkbox.isChecked() is show_annotated
    assert file_tree.show_unannotated_checkbox.isChecked() is not show_annotated
    assert items[new.as_posix()].checkState(0) == QtCore.Qt.Checked
    assert items[old.as_posix()].checkState(0) == QtCore.Qt.Unchecked


def test_update_state_only_updates_existing_annotation_checks(file_tree, tmp_path):
    image = tmp_path / "existing.png"
    write_image(image)
    file_tree.set_root_dir(str(tmp_path))
    item = items_by_path(file_tree.tree_widget)[image.as_posix()]
    file_tree.setCurrentItem(item)
    write_image(image, annotated=True)
    write_image(tmp_path / "added-folder" / "new.png")

    file_tree.update_state()

    assert item.checkState(0) == QtCore.Qt.Checked
    assert file_tree.currentItem() is item
    assert set(items_by_path(file_tree.tree_widget)) == {image.as_posix()}
    image.with_suffix(".json").unlink()
    file_tree.update_state()
    assert item.checkState(0) == QtCore.Qt.Unchecked
