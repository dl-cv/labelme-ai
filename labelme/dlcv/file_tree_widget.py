import os
from pathlib import Path

import natsort
from ordered_set import OrderedSet
from qtpy import QtCore, QtWidgets, QtGui
from qtpy.QtCore import Qt

from labelme.dlcv.store import STORE
from labelme.dlcv.dlcv_translator import dlcv_tr


class FileTreeItem(QtWidgets.QTreeWidgetItem):

    def __init__(self, parent=None):
        super().__init__(parent)

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

        # 设置图标
        self._folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
        self._file_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)

        # 连接信号
        self.itemClicked.connect(self._on_item_clicked)
        self.itemExpanded.connect(self._on_item_expanded)

    @property
    def extensions(self):
        if self._extensions is None:
            self._extensions = tuple(
                fmt.data().decode().lower()
                for fmt in QtGui.QImageReader.supportedImageFormats()
            )
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

    def _load_directory_contents(self, dir_path: str, parent_item: FileTreeItem):
        """加载指定目录的内容
        
        加载指定目录下的所有子文件夹和图片文件。
        为每个文件夹添加占位符节点，实现递归的懒加载。
        检查图片文件是否有对应的标注文件，并设置复选框状态。
        
        Args:
            dir_path: 要加载的目录路径
            parent_item: 父节点对象
        """
        dir_items = []  # #type: list[tuple["file_name", "file_path"]]
        file_items = []  # #type: list[tuple["file_name", "file_path", "checked"]]

        for item_name in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item_name)
            item_path = str(Path(item_path).absolute().as_posix())  # 使用 linux 路径

            if os.path.isdir(item_path):
                dir_items.append([item_name, item_path])
            elif os.path.isfile(item_path) and item_name.lower().endswith(self.extensions):
                # extra 2.5D模式：使用正确的JSON路径获取方法
                if STORE.main_window.is_2_5d:
                    json_path = STORE.main_window.proj_2_5d_manager.get_json_path(item_path)
                else:
                    json_path = STORE.main_window.proj_manager.get_json_path(item_path)
                
                checked = False
                if os.path.exists(json_path):
                    # extra 2.5D模式：检查图片名是否在JSON的imagePath列表中
                    if STORE.main_window.is_2_5d:
                        checked = STORE.main_window.proj_2_5d_manager.is_image_in_json(item_path, json_path)
                    else:
                        checked = True
                file_items.append([item_name, item_path, checked])

        # 对收集的项目进行自然排序
        dir_items = natsort.os_sorted(dir_items, key=lambda x: x[0])
        file_items = natsort.os_sorted(file_items, key=lambda x: x[0])

        # 添加排序后的文件夹
        for item, item_path in dir_items:
            dir_item = FileTreeItem(parent_item)
            dir_item.setText(0, item)
            dir_item.setData(0, Qt.UserRole, item_path)
            dir_item.setFlags(Qt.ItemIsEnabled)
            dir_item.setIcon(0, self._folder_icon)
            # 添加占位符子节点
            QtWidgets.QTreeWidgetItem(dir_item)

        # 添加排序后的文件
        for file, file_path, checked in file_items:
            self._add_file(file_path, checked, parent_item)

    def _add_file(self, file_path: str, checked: bool = False, parent_item: FileTreeItem = None):
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
        file_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        file_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        # file_item.setIcon(0, self._file_icon)

        # 存储映射关系
        self._file_items[file_path] = file_item
        self.image_list.add(file_path)  # 使用 add 方法添加元素到有序集合

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

        self._root_dir = root_dir  # 保存根目录路径
        self.clear()
        # 只加载根目录下的文件夹
        root_item = self.invisibleRootItem()
        self._load_directory_contents(root_dir, root_item)

    def get_root_dir(self) -> str:
        """获取当前根目录路径"""
        return self._root_dir

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
        if not STORE.main_window:
            print(f'update_state: STORE.main_window is None')
            return
        
        is_2_5d = STORE.main_window.is_2_5d
        
        for img_path, file_item in self._file_items.items():
            img_path = file_item.get_path()
            # extra 2.5D模式：使用正确的JSON路径获取方法
            if is_2_5d:
                json_path = STORE.main_window.proj_2_5d_manager.get_json_path(img_path)
            else:
                json_path = STORE.main_window.proj_manager.get_json_path(img_path)
            
            checked = False
            if os.path.exists(json_path):
                # extra 2.5D模式：检查图片名是否在JSON的imagePath列表中
                if is_2_5d:
                    checked = STORE.main_window.proj_2_5d_manager.is_image_in_json(img_path, json_path)
                else:
                    checked = True
            file_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

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

            open_file_action = menu.addAction(dlcv_tr("打开文件"))
            display_in_explorer_action = menu.addAction(dlcv_tr("打开所在目录"))
            menu.addSeparator()
            copy_file_name_action = menu.addAction(dlcv_tr("复制文件名"))
            copy_path_action = menu.addAction(dlcv_tr("复制路径"))
            menu.addSeparator()
            copy_to_clipboard_action = menu.addAction(dlcv_tr("复制文件到剪贴板"))

            display_in_explorer_action.triggered.connect(open_in_explorer)
            copy_path_action.triggered.connect(
                lambda: QtWidgets.QApplication.clipboard().setText(item.
                                                                   get_path()))
            copy_file_name_action.triggered.connect(
                lambda: QtWidgets.QApplication.clipboard().setText(
                    item.super_text(0)))
            open_file_action.triggered.connect(open_file)
            copy_to_clipboard_action.triggered.connect(copy_to_clipboard)

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

    def search(self, text: str):
        """ 根据字符串隐藏 items

        Args:
            text (str): 用于过滤的字符串，只有路径中包含该字符串的文件会显示，其余隐藏
        """
        # 先全部显示
        for img_path, file_item in self._file_items.items():
            file_item.setHidden(False)
        # 隐藏不包含关键字的项
        for img_path in self.image_list:
            if text not in img_path:
                item = self._file_items[img_path]
                item.setHidden(True)

    # ----------- fileListWidget 额外函数 -------------

    def currentRow(self):
        """ load file 的时候，使用了该函数 """
        current_item = self.currentItem()
        if current_item is None:
            return -1

        current_path = current_item.get_path()
        return self.image_list.index(current_path) if current_path in self.image_list else -1

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

    def findItems(self, text, p_str=None, *args, **kwargs) -> list[FileTreeItem]:
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
                gray_img_path = STORE.main_window.proj_manager.get_gray_img_path(text)
                depth_img_path = STORE.main_window.proj_manager.get_depth_img_path(text)

                gray_img_item = self._file_items.get(gray_img_path)
                depth_img_item = self._file_items.get(depth_img_path)
                return list(filter(None, [gray_img_item, depth_img_item]))
            else:
                item = self._file_items[text]
                return [item]
        except KeyError:
            from labelme.dlcv.utils_func import notification, ToastPreset
            notification(title=dlcv_tr("未找到 {text} 文件路径").format(text=text), text=dlcv_tr("代码不应该运行到这里"), preset=ToastPreset.ERROR)
            return []


class FileTreeWidget(QtWidgets.QWidget):
    """文件树类，包含过滤搜索框和树形控件"""

    sig_file_selected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 创建搜索框
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText(dlcv_tr("输入关键字过滤 - Enter键搜索"))
        self.search_box.setToolTip(dlcv_tr("Enter键搜索"))
        self.layout.addWidget(self.search_box)

        # 创建树控件
        self.tree_widget = _FileTreeWidget(self)
        self.layout.addWidget(self.tree_widget)

        # 连接搜索信号
        self.search_box.returnPressed.connect(self._on_search)
        # 监听文本变化，当清空时自动显示所有文件
        self.search_box.textChanged.connect(self._on_text_changed)

    def _on_search(self):
        """处理搜索事件"""
        search_text = self.search_box.text().strip()
        print(f"搜索关键词: '{search_text}'")
        self.tree_widget.search(search_text)

    def _on_text_changed(self, text):
        """处理文本变化事件"""
        # 当搜索框被清空时，自动显示所有文件
        if not text.strip():
            print("搜索框已清空，显示所有文件")
            self.tree_widget.search("")
 
    def __getattr__(self, name):
        """
        代理属性访问，将属性访问转发给 tree_widget 对象
        """
        if hasattr(self.tree_widget, name):
            return getattr(self.tree_widget, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def keyPressEvent(self, event):
        self.tree_widget.keyPressEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = FileTreeWidget()

    # dir_path = "C:\dlcv\datasets\dogs_vs_cats\狗"
    dir_path = r"C:\Users\Admin\Pictures"
    w.set_root_dir(dir_path)

    w.show()
    app.exec_()
