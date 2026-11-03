import os
from dataclasses import replace
from pathlib import Path

from dlcv_core.image_json import ImageJsonError, UnsupportedImageFormatError

import natsort
from ordered_set import OrderedSet
from qtpy import QtCore, QtWidgets, QtGui
from qtpy.QtCore import Qt

from labelme.dlcv.dlcv_translator import dlcv_tr
from labelme.dlcv.label_file import has_image_json
from labelme.dlcv.store import STORE
from labelme.dlcv.widget.file_tree_filter import FileTreeFilter
from labelme.dlcv.widget.file_tree_filter import TreeFilter
from labelme.dlcv.widget.image_filter_panel import image_key
from labelme.dlcv.widget.image_filter_widget import ImageFilterWidget


def _has_embedded_annotation(image_path):
    try:
        return has_image_json(image_path)
    except UnsupportedImageFormatError:
        return False
    except (ImageJsonError, OSError) as exc:
        from labelme.dlcv.utils_func import notification, ToastPreset

        notification(
            dlcv_tr("读取标注失败"), f"{image_path}: {exc}", ToastPreset.ERROR
        )
        return False


class FileTreeItem(QtWidgets.QTreeWidgetItem):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def text(self):
        return self.get_path()

    def get_path(self):
        return self.data(0, Qt.UserRole)

    def super_text(self, column):
        return super().text(column)

    def setCheckState(self, state):
        super().setCheckState(0, state)


class _FileTreeWidget(QtWidgets.QTreeWidget):
    """文件树控件，用于显示和管理标注文件
    
    这个控件继承自QTreeWidget，实现了一个支持懒加载的文件树。
    主要用于显示和管理图片文件及其对应的标注文件。
    支持文件夹展开时动态加载内容，提高大型目录的加载性能。
    """

    sig_file_selected = QtCore.Signal(str)  # 文件选中信号
    sig_delete_requested = QtCore.Signal(object)  # 删除请求信号，参数为 list[str]

    def __init__(self, parent=None):
        """初始化文件树控件
        
        Args:
            parent: 父窗口对象
        """
        super().__init__(parent)
        self.setHeaderLabels(["文件"])
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        # 属性
        self._root_dir = None
        self._file_items = {}  # 存储文件路径到树item的映射
        self.image_list = OrderedSet()  # 存储所有图片文件的路径列表，使用有序集合.为 as_posix 格式
        self._extensions = None  # 存储所有图片文件的扩展名 [".jpg", ".png", ".jpeg", ".bmp", ".tif", ".tiff", ".dng", ".webp"]

        # 过滤执行器：条件对象 + 应用到树上的逻辑统一在 TreeFilter 里
        self._tree_filter = TreeFilter(
            self, lambda: self._file_items, path_key=image_key
        )

        # 设置图标
        self._folder_icon = self.style().standardIcon(
            QtWidgets.QStyle.SP_DirIcon)
        self._file_icon = self.style().standardIcon(
            QtWidgets.QStyle.SP_FileIcon)

        # 连接信号
        self.itemClicked.connect(self._on_item_clicked)
        self.itemExpanded.connect(self._on_item_expanded)

    @property
    def extensions(self):
        if self._extensions is None:
            self._extensions = tuple(
                fmt.data().decode().lower()
                for fmt in QtGui.QImageReader.supportedImageFormats())
        return self._extensions

    def _on_item_clicked(self, item, column):
        """处理项目点击事件

        当用户点击文件节点时，发出文件选中信号。
        只处理文件节点（没有子节点的项目），忽略文件夹节点。

        Args:
            item: 被点击的树节点
            column: 被点击的列索引
        """
        if item.childCount() == 0:  # 只处理文件节点
            file_path = item.data(0, Qt.UserRole)
            if file_path:
                self.sig_file_selected.emit(file_path)

    # ----------- 处理项目展开事件 -------------
    def _on_item_expanded(self, item):
        """处理项目展开事件

        当用户展开文件夹节点时，加载该文件夹的内容。
        通过检查是否存在占位符节点来判断是否需要加载内容。

        Args:
            item: 被展开的树节点
        """
        if item.childCount() == 1:  # 可能是占位符节点
            child_item = item.child(0)
            # 检查子节点是否为占位符（兼容FileTreeItem和QTreeWidgetItem两种类型）
            child_text = ""
            if isinstance(child_item, FileTreeItem):
                child_text = child_item.super_text(0)
            else:  # QTreeWidgetItem
                child_text = child_item.text(0)

            if child_text == "":  # 确认是占位符节点
                item.takeChild(0)  # 移除占位符
                dir_path = item.data(0, Qt.UserRole)
                self._load_directory_contents(dir_path, item)

    def _load_directory_contents(self, dir_path: str,
                                 parent_item: FileTreeItem):
        """加载指定目录的内容

        加载指定目录下的所有子文件夹和图片文件。
        为每个文件夹添加占位符节点，实现递归的懒加载。
        检查图片文件是否有对应的标注文件，并设置复选框状态。

        Args:
            dir_path: 要加载的目录路径
            parent_item: 父节点对象
        """
        dir_items = []  # #type: list[tuple["file_name", "file_path"]]
        file_items = [
        ]  # #type: list[tuple["file_name", "file_path", "checked"]]

        # scandir: 一次枚举；entry.is_dir/is_file 尽量用目录缓存，少网络 stat
        try:
            entries = list(os.scandir(dir_path))
        except OSError:
            return

        # 同目录内 json 是否存在：用文件名集合判断，避免每张图 os.path.exists
        # （2D/3D/2.5D 的 get_json_path 结果都在图片同目录）
        name_set_lower = {e.name.lower() for e in entries}

        extensions = self.extensions
        proj_manager = STORE.main_window.proj_manager
        dir_base = str(Path(dir_path).absolute().as_posix()).rstrip("/")

        for entry in entries:
            item_name = entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue

            item_path = f"{dir_base}/{item_name}"

            if is_dir:
                dir_items.append([item_name, item_path])
                continue

            try:
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if not is_file or not item_name.lower().endswith(extensions):
                continue

            # 仍走项目 get_json_path（2D/3D/2.5D 规则不同），仅存在性用 name_set
            json_path = proj_manager.get_json_path(item_path)
            json_name = os.path.basename(json_path).lower()
            checked = json_name in name_set_lower
            file_items.append([item_name, item_path, checked])

        # 对收集的项目进行自然排序
        dir_items = natsort.os_sorted(dir_items, key=lambda x: x[0])
        file_items = natsort.os_sorted(file_items, key=lambda x: x[0])

        # 添加排序后的文件夹
        for item, item_path in dir_items:
            dir_item = FileTreeItem(parent_item)
            dir_item.setText(0, item)
            dir_item.setData(0, Qt.UserRole, item_path)

            dir_item.setIcon(0, self._folder_icon)
            # 添加占位符子节点
            QtWidgets.QTreeWidgetItem(dir_item)
            self.apply_filter_to_item(dir_item, self.filter_state)

        # 添加排序后的文件
        for file, file_path, checked in file_items:
            self._add_file(file_path, checked, parent_item)

    def _add_file(self,
                  file_path: str,
                  checked: bool = False,
                  parent_item: FileTreeItem = None):
        """添加文件到树中

        创建文件节点并设置其属性，包括文本、图标、复选框状态等。
        如果文件已有对应的标注文件，则设置复选框为选中状态。

        Args:
            file_path: 文件路径
            checked: 是否选中复选框
            parent_item: 父节点对象，如果为None则自动创建
        """
        if file_path in self._file_items:
            return

        assert parent_item is not None

        file_name = Path(file_path).name

        # 创建文件节点
        file_item = FileTreeItem(parent_item)
        file_item.setText(0, file_name)
        file_item.setData(0, Qt.UserRole, file_path)
        file_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        # file_item.setIcon(0, self._file_icon)

        # 存储映射关系
        self._file_items[file_path] = file_item
        self.image_list.add(file_path)  # 使用 add 方法添加元素到有序集合
        self.apply_filter_to_item(file_item, self.filter_state)

    # ----------- 处理项目展开事件 End ----------

    def set_root_dir(self, root_dir: str):
        """设置根目录路径，只加载目录结构

        设置文件树的根目录，并只加载根目录下的文件夹结构。
        使用懒加载机制，初始只显示文件夹，不加载文件。

        Args:
            root_dir: 根目录的路径
        """
        if not root_dir or not os.path.exists(root_dir):
            return

        self.clear()

        self._root_dir = root_dir  # 保存根目录路径
        # 只加载根目录下的文件夹
        root_item = self.invisibleRootItem()
        self._load_directory_contents(root_dir, root_item)

    def get_root_dir(self) -> str:
        """获取当前根目录路径"""
        return self._root_dir

    @staticmethod
    def _path_key(path) -> str:
        if not path:
            return ""
        try:
            return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))
        except (OSError, TypeError, ValueError):
            return ""

    @staticmethod
    def _is_effectively_hidden(item) -> bool:
        """item 自身或任一祖先被隐藏（筛选时父目录隐藏，子文件自身仍是 False）。"""
        while item is not None:
            if item.isHidden():
                return True
            item = item.parent()
        return False

    def _find_file_item(self, file_path: str):
        """按文件路径查找已加载的树节点（兼容大小写/斜杠差异）。"""
        if not file_path:
            return None
        try:
            posix_path = Path(file_path).absolute().as_posix()
        except (OSError, TypeError, ValueError):
            posix_path = ""
        item = self._file_items.get(posix_path)
        if item is not None:
            return item

        expected_key = self._path_key(file_path)
        for path, file_item in self._file_items.items():
            if self._path_key(path) == expected_key:
                return file_item
        return None

    def _find_child_dir_item(self, parent_item, directory):
        expected_key = self._path_key(directory)
        for index in range(parent_item.childCount()):
            child = parent_item.child(index)
            child_path = child.data(0, Qt.UserRole)
            if child_path and self._path_key(child_path) == expected_key:
                return child
        return None

    def _ensure_directory_loaded(self, item) -> None:
        """展开懒加载目录节点，把子节点真正创建出来。"""
        if item.childCount() == 1:
            placeholder = item.child(0)
            if not placeholder.data(0, Qt.UserRole):
                self._on_item_expanded(item)
        item.setExpanded(True)

    def _ensure_file_item(self, file_path: str):
        """逐级展开父目录，直到目标文件节点被加载。"""
        item = self._find_file_item(file_path)
        if item is not None:
            return item
        if not self._root_dir:
            return None
        try:
            root_path = Path(self._root_dir).absolute()
            target_path = Path(file_path).absolute()
            relative = target_path.relative_to(root_path)
        except (OSError, TypeError, ValueError):
            return None

        parent_item = self.invisibleRootItem()
        current_path = root_path
        for part in relative.parts[:-1]:
            current_path = current_path / part
            directory_item = self._find_child_dir_item(parent_item, current_path)
            if directory_item is None:
                return None
            self._ensure_directory_loaded(directory_item)
            parent_item = directory_item
        return self._find_file_item(file_path)

    def select_file_path(self, file_path: str):
        """展开并选中指定文件，选中后由主窗的选中信号负责加载图片。

        返回对应的树节点；找不到时返回 None。
        """
        item = self._ensure_file_item(file_path)
        if item is None:
            return None
        self.setCurrentItem(item, 0)
        self.scrollToItem(item, 0)
        if not item.isSelected():
            item.setSelected(True)
        return item

    def first_file_path(self) -> str | None:
        """返回文件树中可见的第一个图片路径（优先当前目录的文件）。"""
        root = self.invisibleRootItem()

        for index in range(root.childCount()):
            child = root.child(index)
            path = child.data(0, Qt.UserRole)
            if path and path in self._file_items:
                if not self._is_effectively_hidden(child):
                    return path

        def _first_in_children(parent_item):
            for index in range(parent_item.childCount()):
                child = parent_item.child(index)
                path = child.data(0, Qt.UserRole)
                if not path or path in self._file_items:
                    continue
                if self._is_effectively_hidden(child):
                    continue
                self._ensure_directory_loaded(child)
                for sub_index in range(child.childCount()):
                    sub_item = child.child(sub_index)
                    sub_path = sub_item.data(0, Qt.UserRole)
                    if sub_path and sub_path in self._file_items:
                        if not self._is_effectively_hidden(sub_item):
                            return sub_path
                found = _first_in_children(child)
                if found:
                    return found
            return None

        return _first_in_children(root)

    def refresh_directory(self):
        if not self._root_dir or not os.path.isdir(self._root_dir):
            return

        directory_states = {}
        selected_paths = {item.get_path() for item in self.selectedItems()}
        current = self.currentItem()
        current_path = current.get_path() if current else None
        scroll_value = self.verticalScrollBar().value()
        iterator = QtWidgets.QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            path = item.data(0, Qt.UserRole)
            if path and path not in self._file_items:
                loaded = (item.childCount() == 0 or
                          bool(item.child(0).data(0, Qt.UserRole)))
                directory_states[path] = (loaded, item.isExpanded())
            iterator += 1

        # 重建时阻止选择变化触发图片重载，保留当前画布及未保存编辑。
        blocker = QtCore.QSignalBlocker(self)
        try:
            self.set_root_dir(self._root_dir)

            def restore_items(parent):
                for index in range(parent.childCount()):
                    item = parent.child(index)
                    path = item.data(0, Qt.UserRole)
                    if path is None:
                        continue
                    loaded, expanded = directory_states.get(path, (False, False))
                    if loaded or expanded:
                        self._on_item_expanded(item)
                    if path == current_path:
                        self.setCurrentItem(item, 0, QtCore.QItemSelectionModel.NoUpdate)
                    item.setSelected(path in selected_paths)
                    restore_items(item)
                    # Qt 恢复当前子项时会展开父目录，最后再恢复目录状态。
                    item.setExpanded(expanded)

            restore_items(self.invisibleRootItem())
        finally:
            blocker.unblock()
        self.verticalScrollBar().setValue(scroll_value)

    def clear(self):
        """清空文件树

        清空所有节点和文件映射。
        """
        super().clear()
        self._file_items.clear()
        self.image_list.clear()  # 清空有序集合
        self._root_dir = None

    def currentItem(self) -> FileTreeItem:
        return super().currentItem()

    def update_state(self):
        """更新所有文件项的勾选状态"""
        # 按目录缓存一次 scandir 文件名，避免每张图 exists 打网盘
        dir_name_cache = {}
        proj_manager = STORE.main_window.proj_manager

        def _names_lower(dir_path: str):
            if dir_path not in dir_name_cache:
                try:
                    dir_name_cache[dir_path] = {
                        e.name.lower()
                        for e in os.scandir(dir_path)
                    }
                except OSError:
                    dir_name_cache[dir_path] = set()
            return dir_name_cache[dir_path]

        for img_path, file_item in self._file_items.items():
            img_path = file_item.get_path()
            json_path = proj_manager.get_json_path(img_path)
            json_dir = os.path.dirname(json_path)
            json_name = os.path.basename(json_path).lower()
            checked = json_name in _names_lower(json_dir)
            file_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def delete_item(self, items: list[FileTreeItem]):
        deleted_paths = set()
        for item in items:
            if item is None:
                continue
            file_path = item.get_path()
            if not file_path:
                continue
            deleted_paths.add(file_path)

            self._file_items.pop(file_path, None)
            parent_item = item.parent()
            if parent_item is not None:
                parent_item.removeChild(item)
            else:
                self.invisibleRootItem().removeChild(item)

        if deleted_paths:
            self.image_list = OrderedSet(
                [p for p in self.image_list if p not in deleted_paths]
            )

    def contextMenuEvent(self, event):

        def context_folder_menu(item, event):
            menu = QtWidgets.QMenu(self)

            def _expand_all_subfolders(item):
                """递归展开所有子文件夹"""
                if not item.isExpanded():
                    item.setExpanded(True)
                for i in range(item.childCount()):
                    child = item.child(i)
                    if child.childCount() > 0:
                        _expand_all_subfolders(child)

            def expand_all():
                _expand_all_subfolders(item)

            expand_action = menu.addAction(dlcv_tr("展开所有子文件夹"))
            expand_action.triggered.connect(expand_all)
            menu.exec_(self.viewport().mapToGlobal(event.pos()))

        def context_file_nemu(items: list[FileTreeItem]):
            menu = QtWidgets.QMenu(self)

            def copy_to_clipboard():
                from labelme.dlcv.widget.clipboard import copy_files_to_clipboard
                from labelme.dlcv.utils_func import notification, ToastPreset

                file_paths = [item.get_path() for item in items]
                file_paths = [
                    file_path for file_path in file_paths
                    if os.path.exists(file_path)
                ]
                copy_files_to_clipboard(file_paths)
                notification(
                    title=dlcv_tr("复制文件到剪贴板成功"),
                    text=dlcv_tr("已将文件复制到剪贴板"),
                    preset=ToastPreset.SUCCESS)

            def open_in_explorer():
                current_path = self.currentItem().get_path()
                current_path = str(Path(current_path).absolute())
                os.system(f'explorer /select,"{current_path}"')

            def open_file():
                current_path = self.currentItem().get_path()
                current_path = str(Path(current_path).absolute())
                os.system(f'start "" "{current_path}"')

            def delete_images_and_labels():
                file_paths = []
                for file_item in items:
                    if file_item and file_item.childCount() == 0:
                        file_path = file_item.get_path()
                        if file_path:
                            file_paths.append(str(Path(file_path).absolute().as_posix()))
                if file_paths:
                    self.sig_delete_requested.emit(file_paths)

            open_file_action = menu.addAction(dlcv_tr("打开文件"))
            display_in_explorer_action = menu.addAction(dlcv_tr("打开所在目录"))
            menu.addSeparator()
            copy_file_name_action = menu.addAction(dlcv_tr("复制文件名"))
            copy_path_action = menu.addAction(dlcv_tr("复制路径"))
            copy_to_clipboard_action = menu.addAction(dlcv_tr("复制文件到剪贴板"))
            menu.addSeparator()
            delete_action = menu.addAction(dlcv_tr("删除图片及标注"))

            display_in_explorer_action.triggered.connect(open_in_explorer)
            copy_path_action.triggered.connect(
                lambda: QtWidgets.QApplication.clipboard().setText(
                    os.path.abspath(item.get_path())))
            copy_file_name_action.triggered.connect(
                lambda: QtWidgets.QApplication.clipboard().setText(
                    item.super_text(0)))
            open_file_action.triggered.connect(open_file)
            copy_to_clipboard_action.triggered.connect(copy_to_clipboard)
            delete_action.triggered.connect(delete_images_and_labels)

            menu.exec_(self.viewport().mapToGlobal(event.pos()))

        item = self.itemAt(event.pos())
        select_items = self.selectedItems()

        # 如果点击的是文件夹，则显示文件夹菜单
        if item and item.childCount() > 0:
            context_folder_menu(item, event)

        if len(select_items) > 0:
            context_file_nemu(select_items)

    def mouseReleaseEvent(self, event):
        # 在鼠标释放时也检查 Shift 键的状态
        if not (event.modifiers() & Qt.ShiftModifier):  # 如果 Shift 键没有按下
            self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            self.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        super().mousePressEvent(event)

    @property
    def filter_state(self) -> FileTreeFilter:
        return self._tree_filter.criteria

    def reset_filter(self):
        """清空所有过滤条件，并恢复本功能隐藏的目录。"""
        self._tree_filter.reset()

    def set_filter(self, filter_state: FileTreeFilter):
        """应用统一过滤条件（文件名 + 标注状态 + 类别）。"""
        self._tree_filter.apply(filter_state)

    def apply_filter_to_item(self, item, filter_state: FileTreeFilter) -> None:
        """对单个节点应用过滤（懒加载/勾选状态变化时使用）。"""
        self._tree_filter.apply_to_item(item, filter_state)

    def search(self, text: str):
        """按文件名搜索；标注状态和类别筛选条件保持不变。"""
        self._tree_filter.apply(
            replace(self._tree_filter.criteria, search_text=text)
        )

    # ----------- fileListWidget 额外函数 -------------

    def currentRow(self):
        """ load file 的时候，使用了该函数 """
        current_item = self.currentItem()
        if current_item is None:
            return -1

        current_path = current_item.get_path()
        return self.image_list.index(
            current_path) if current_path in self.image_list else -1

    def setCurrentRow(self, row):
        """ load file 的时候，使用了该函数 """
        item_path = self.image_list[row]
        item = self._file_items.get(item_path)
        self.setCurrentItem(item)

    def count(self):
        return len(self.image_list)

    def item(self, row):
        """ 自动标注使用了该函数 """
        return self._file_items.get(self.image_list[row])

    def findItems(self,
                  text,
                  p_str=None,
                  *args,
                  **kwargs) -> list[FileTreeItem]:
        """
        text 是文件路径
        更改 checkState 的时候，使用了该函数，详情查看   def saveLabels(self, filename):

        在文件树中搜索匹配特定文本的项目
        Args:
            text: 文件路径
            p_str: Qt 匹配模式，如 Qt.MatchContains, Qt.MatchStartsWith 等
            *args: 其他参数
            **kwargs: 其他关键字参数

        Returns:
            list[FileTreeItem]: 匹配的项目列表
        """
        text = Path(text).absolute().as_posix()

        try:
            if STORE.main_window.is_3d:
                gray_img_path = STORE.main_window.proj_manager.get_gray_img_path(
                    text)
                depth_img_path = STORE.main_window.proj_manager.get_depth_img_path(
                    text)

                gray_img_item = self._file_items.get(gray_img_path)
                depth_img_item = self._file_items.get(depth_img_path)
                return list(filter(None, [gray_img_item, depth_img_item]))
            else:
                item = self._file_items[text]
                return [item]
        except KeyError:
            from labelme.dlcv.utils_func import notification, ToastPreset
            notification(
                title=dlcv_tr("未找到 {text} 文件路径").format(text=text),
                text=dlcv_tr(f'请检查图片文件是否存在，是否是 ')
                +STORE.main_window.parameter.child("proj_setting", "proj_type").value()
                +dlcv_tr(' 类型，标注文件是否正确')
                ,
                preset=ToastPreset.ERROR)
            return []


def _confirm_delete_dialog(parent: QtWidgets.QWidget, count: int) -> bool:
    msg_box = QtWidgets.QMessageBox
    yes, no = msg_box.Yes, msg_box.No
    confirm = msg_box.question(
        parent,
        dlcv_tr("确认删除"),
        dlcv_tr("你将要删除选中的 {count} 张图片及其标注文件，是否继续？").format(
            count=count
        ),
        yes | no,
        no,
    )
    return confirm == yes


def _clear_current_file_state(tree_widget: _FileTreeWidget):
    main_window = STORE.main_window
    if main_window is None:
        return
    main_window.resetState()
    main_window.canvas.loadPixmap(QtGui.QPixmap())
    main_window.filename = None
    tree_widget.clearSelection()


def _show_delete_result_dialog(
    parent: QtWidgets.QWidget, deleted_count: int, failed: list[tuple[str, str]]
):
    msg_box = QtWidgets.QMessageBox
    if failed:
        msg_box.warning(
            parent,
            dlcv_tr("删除部分失败"),
            dlcv_tr("成功删除 {success} 张，失败 {failed} 张。").format(
                success=deleted_count, failed=len(failed)
            ),
        )
    else:
        msg_box.information(
            parent,
            dlcv_tr("删除完成"),
            dlcv_tr("已删除 {count} 张图片。").format(count=deleted_count),
        )


class FileTreeWidget(QtWidgets.QWidget):
    """文件树类，包含过滤搜索框和树形控件"""

    sig_file_selected = QtCore.Signal(str)
    sig_delete_requested = QtCore.Signal(object)  # 参数为 list[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        # 供 QSS 精准命中
        self.setObjectName("fileListPanel")
        self.layout = QtWidgets.QVBoxLayout(self)
        # 贴近截图的“卡片内边距/间距”
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(8)

        # 创建搜索框
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setObjectName("fileSearch")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setPlaceholderText(dlcv_tr("搜索文件名"))
        self.search_box.setToolTip(dlcv_tr("Enter键搜索"))

        # “图像筛选”入口：点击后在文件树面板内展开筛选组件
        self.image_filter_btn = QtWidgets.QToolButton(self)
        self.image_filter_btn.setObjectName("fileFilterBtn")
        self.image_filter_btn.setIconSize(QtCore.QSize(16, 16))
        self.image_filter_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.image_filter_btn.setCursor(Qt.PointingHandCursor)
        self.image_filter_btn.setFixedSize(32, 32)
        self.image_filter_btn.setToolTip(dlcv_tr("按标注类别筛选图片"))
        self.image_filter_btn.setAccessibleName(dlcv_tr("图像筛选"))

        search_row = QtWidgets.QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.image_filter_btn)
        self.layout.addLayout(search_row)

        # 创建过滤选项栏
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)

        self.show_annotated_checkbox = QtWidgets.QCheckBox()
        self.show_annotated_checkbox.setText(dlcv_tr("已标注"))
        self.show_annotated_checkbox.setToolTip(
            dlcv_tr("显示已有标注文件(JSON)的图片"))
        filter_layout.addWidget(self.show_annotated_checkbox)

        self.show_unannotated_checkbox = QtWidgets.QCheckBox()
        self.show_unannotated_checkbox.setText(dlcv_tr("未标注"))
        self.show_unannotated_checkbox.setToolTip(
            dlcv_tr("显示没有标注文件的图片"))
        filter_layout.addWidget(self.show_unannotated_checkbox)
        filter_layout.addStretch()

        self.layout.addLayout(filter_layout)

        # 创建树控件
        self.tree_widget = _FileTreeWidget(self)
        self.tree_widget.setObjectName("fileTree")

        # 图像筛选组件：与文件树共用同一块区域，展开时替换文件树
        self.image_filter = ImageFilterWidget(
            tree_widget=self.tree_widget,
            owner=self,
            toggle_button=self.image_filter_btn,
            parent=self,
        )
        self._body_stack = QtWidgets.QStackedWidget(self)
        self._body_stack.setObjectName("fileTreeStack")
        self._body_stack.addWidget(self.tree_widget)
        self._body_stack.addWidget(self.image_filter)
        self._body_stack.setCurrentWidget(self.tree_widget)
        self.layout.addWidget(self._body_stack)
        self.image_filter.sig_open_changed.connect(self._on_filter_page_changed)

        # 连接搜索信号
        self.search_box.returnPressed.connect(self._on_search)
        # 监听文本变化，当清空时自动显示所有文件
        self.search_box.textChanged.connect(self._on_text_changed)
        # 删除请求在当前组件内处理
        self.tree_widget.sig_delete_requested.connect(self._on_delete_requested)
        self.tree_widget.itemChanged.connect(self._on_item_changed)
        # 监听标注状态复选框变化
        self.show_annotated_checkbox.stateChanged.connect(
            self._on_filter_changed)
        self.show_unannotated_checkbox.stateChanged.connect(
            self._on_filter_changed)

    # ---------- 图像筛选（组件） ----------

    def _on_filter_page_changed(self, is_open: bool):
        self._body_stack.setCurrentWidget(
            self.image_filter if is_open else self.tree_widget
        )
        if not is_open:
            self.tree_widget.setFocus()

    def reapply_filters(self):
        """由图像筛选组件调用：按当前筛选状态重新过滤文件树。"""
        self._apply_filters()

    def mark_category_dirty(self):
        """标注数据变化后通知图像筛选组件重新统计类别。"""
        self.image_filter.mark_data_changed()

    def closeEvent(self, event):
        self.image_filter.shutdown()
        super().closeEvent(event)

    def set_root_dir(self, root_dir):
        self.image_filter.reset_for_new_root()
        self.tree_widget.reset_filter()
        self.tree_widget.set_root_dir(root_dir)

    def clear(self):
        self.image_filter.reset_for_new_root()
        self.tree_widget.reset_filter()
        self.tree_widget.clear()

    def update_state(self):
        self.tree_widget.update_state()
        self.image_filter.notify_tree_changed()

    def refresh_directory(self):
        self.tree_widget.refresh_directory()
        self.image_filter.notify_tree_changed()
        self._apply_filters()

    def _on_delete_requested(self, file_paths: list[str]):
        if not file_paths:
            return

        file_paths = [str(Path(p).absolute().as_posix()) for p in file_paths if p]
        if not file_paths:
            return

        if not _confirm_delete_dialog(self, len(file_paths)):
            return

        main_window = STORE.main_window
        if main_window is None:
            return

        current_file = getattr(main_window, "filename", None)
        current_file_abs = (
            str(Path(current_file).absolute().as_posix()) if current_file else None
        )

        deleted_current = False
        deleted_count = 0
        failed = []
        for img_path_abs in file_paths:
            if current_file_abs and img_path_abs == current_file_abs:
                deleted_current = True
            try:
                json_path = main_window.proj_manager.get_json_path(img_path_abs)
                if os.path.exists(img_path_abs):
                    os.remove(img_path_abs)
                    deleted_count += 1
                if json_path and os.path.exists(json_path):
                    os.remove(json_path)
            except Exception as e:
                failed.append((img_path_abs, str(e)))

        items_to_remove = [
            self.tree_widget._file_items.get(path)
            for path in file_paths
            if path in self.tree_widget._file_items
        ]
        self.tree_widget.delete_item(items_to_remove)

        if deleted_current:
            _clear_current_file_state(self.tree_widget)
        _show_delete_result_dialog(self, deleted_count, failed)

        self.image_filter.notify_tree_changed()

    def _current_filter(self) -> FileTreeFilter:
        """根据界面状态和图像筛选组件状态组装统一过滤条件。"""
        categories, index = self.image_filter.filter_state()
        return FileTreeFilter(
            search_text=self.search_box.text().strip(),
            show_annotated=self.show_annotated_checkbox.isChecked(),
            show_unannotated=self.show_unannotated_checkbox.isChecked(),
            categories=frozenset(categories),
            index=index,
        )

    def _on_search(self):
        """回车应用搜索框内容。"""
        self._apply_filters()

    def _on_text_changed(self, text):
        """输入过程中不筛选；清空搜索框时立即恢复全部文件。"""
        if not text.strip():
            self._apply_filters()

    def _on_filter_changed(self, state):
        """处理标注状态复选框变化"""
        self._apply_filters()

    def _on_item_changed(self, item, column):
        show_annotated = self.show_annotated_checkbox.isChecked()
        show_unannotated = self.show_unannotated_checkbox.isChecked()
        if show_annotated == show_unannotated:
            return
        if item.get_path() in self.tree_widget._file_items:
            self.tree_widget.apply_filter_to_item(item, self._current_filter())

    def _apply_filters(self):
        """应用当前所有过滤条件（文件树只负责过滤执行）。"""
        self.tree_widget.set_filter(self._current_filter())

    def apply_filters(self, search_text: str = "",
                      show_annotated: bool = False,
                      show_unannotated: bool = False):
        """兼容外部直接调用：用传入条件 + 当前类别筛选状态重新过滤。"""
        categories, index = self.image_filter.filter_state()
        self.tree_widget.set_filter(
            FileTreeFilter(
                search_text=search_text,
                show_annotated=show_annotated,
                show_unannotated=show_unannotated,
                categories=frozenset(categories),
                index=index,
            )
        )

    def __getattr__(self, name):
        """
        代理属性访问，将属性访问转发给 tree_widget 对象
        """
        if hasattr(self.tree_widget, name):
            return getattr(self.tree_widget, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'")

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self.tree_widget.keyPressEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = FileTreeWidget()

    dir_path = "C:\dlcv\datasets"
    # dir_path = r"C:\Users\Admin\Pictures"
    w.set_root_dir(dir_path)

    w.show()
    app.exec_()
