import sys
import time  # noqa
import traceback
from pathlib import Path

import labelme.dlcv.ai
import labelme.dlcv.label_file
import labelme.dlcv.shape

sys.modules["labelme.shape"] = (
    labelme.dlcv.shape
)  # 使用 from xxx import 时形式导入时, 会导致无法替换, 所以使用 sys.modules
sys.modules["labelme.ai"] = labelme.dlcv.ai  # 替换 ai 模块
sys.modules["labelme.label_file"] = labelme.dlcv.label_file

import labelme.dlcv.canvas
import labelme.widgets

# 旧模块替换, 注意每次写新模块时都要添加
labelme.widgets.canvas = labelme.dlcv.canvas
labelme.widgets.Canvas = labelme.dlcv.canvas.Canvas
labelme.ai = labelme.dlcv.ai
labelme.ai = labelme.dlcv.ai

import cv2
from pyqtgraph.parametertree import Parameter, ParameterTree
from pyqttoast import Toast, ToastPreset
from PIL import ImageFile, Image
import yaml
import json

from labelme import __appname__
from labelme.app import *
from labelme.dlcv.utils_func import notification, normalize_16b_gray_to_uint8
from labelme.dlcv.store import STORE
from labelme.dlcv import dlcv_tr
from labelme.utils.qt import removeAction, newIcon
from shapely.geometry import Polygon, LineString
from shapely.ops import split
from labelme.dlcv.shape import ShapeType
from labelme.utils import print_time  # noqa
from labelme.dlcv.shape import Shape
from labelme.dlcv.widget.viewAttribute import (
    get_shape_attribute,
    get_window_position,
    viewAttribute,
)
from labelme.dlcv.widget.clipboard import copy_file_to_clipboard
import os
from labelme.dlcv.widget.label_count import LabelCountDock
from labelme.dlcv.ui_theme_manager import UiThemeManager

Image.MAX_IMAGE_PIXELS = None  # Image 最大像素限制, 防止加载大图时报错
ImageFile.LOAD_TRUNCATED_IMAGES = True  # 解决图片加载失败问题

# region
# 2025年6月17日 已弃用
# class ImageScanner(QtCore.QThread):
#     sig_scan_done = QtCore.Signal(list)
#     sig_init_item_done = QtCore.Signal(list)

#     def __init__(self, dir_path, pattern=None, output_dir=None):
#         super().__init__()
#         self.dir_path = dir_path
#         self.pattern = pattern
#         self.output_dir = output_dir

#     def run(self):
#         # 扫描图片文件的逻辑
#         filenames = self.scanAllImages(self.dir_path)
#         if self.pattern:
#             try:
#                 filenames = [f for f in filenames if re.search(self.pattern, f)]
#             except re.error:
#                 pass
#         self.sig_scan_done.emit(filenames)

#         items = []
#         for filename in filenames:
#             label_file = osp.splitext(filename)[0] + ".json"
#             if self.output_dir:
#                 label_file_without_path = osp.basename(label_file)
#                 label_file = osp.join(self.output_dir, label_file_without_path)
#             item = QtWidgets.QListWidgetItem(filename)
#             item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
#             if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
#                 item.setCheckState(Qt.Checked)
#             else:
#                 item.setCheckState(Qt.Unchecked)
#             items.append(item)

#         self.sig_init_item_done.emit(items)

#     def scanAllImages(self, dir_path):
#         extensions = [
#             ".%s" % fmt.data().decode().lower()
#             for fmt in QtGui.QImageReader.supportedImageFormats()
#         ]

#         images = []
#         for root, dirs, files in os.walk(dir_path):
#             for file in files:
#                 if file.lower().endswith(tuple(extensions)):
#                     relativePath = os.path.normpath(osp.join(root, file))
#                     images.append(relativePath)
#         images = natsort.os_sorted(images)
#         return images
# endregion


class MainWindow(MainWindow):
    canvas: labelme.dlcv.canvas.Canvas
    sig_auto_label_all_update = QtCore.Signal(object)

    def __init__(
        self, config=None, filename=None, output=None, output_file=None, output_dir=None
    ):
        self.settings = QtCore.QSettings("labelme", "labelme")
        # extra 额外属性
        self.action_refresh = None
        # 2.5D管理器
        STORE.register_main_window(self)
        super().__init__(config, filename, output, output_file, output_dir)

        Toast.setPositionRelativeToWidget(self)  # 通知控件
        self.dev_setting = QtCore.QSettings("baiduyun_dev", "ai")
        
        # 移除 [ImageData] 功能, 默认自动保存
        removeAction(self.menus.file, self.actions.saveWithImageData)
        removeAction(self.menus.file, self.actions.saveAuto)
        # 移除 [更改输出目录] 功能
        removeAction(self.menus.file, self.actions.changeOutputDir)

        # https://bbs.dlcv.ai/t/topic/86
        self.addDockWidget(Qt.LeftDockWidgetArea, self.file_dock)

        #
        branding = getattr(STORE, "branding", None) or {}
        app_cfg = branding.get("App") or branding.get("app") or {}
        v = app_cfg.get("DisplayURL", app_cfg.get("displayurl", None))
        show_help = True if v is None else str(v).strip().lower() not in ("0", "false", "no", "off")
        if show_help:
            self.menus.help.actions()[0].setText(dlcv_tr("使用文档"))
        else:
            self.menus.help.menuAction().setVisible(False)

        self._init_dev_mode()
        self._init_ui()

        # UI 主题由独立组件管理（仅外观，不改功能）
        self.ui_theme_manager = UiThemeManager(main_window=self, settings=self.settings)
        self.ui_theme_manager.apply_from_settings()
        self.actions.copy.setEnabled(True)

        # 修改复制动作的文本
        self.actions.copy.setText(dlcv_tr("复制图片"))

        self._init_edit_mode_action()  # 初始化编辑模式切换动作
        STORE.set_edit_label_name(self._edit_label)

        # 新增设置菜单
        self._init_setting_menu()

        # APPData 目录
        APPDATA_DIR = (
            os.path.expanduser("~")
            + os.sep
            + "AppData"
            + os.sep
            + "Roaming"
            + os.sep
            + "dlcv"
        )  # "C:\Users\{用户名}\AppData\Roaming\dlcv"
        self.LABEL_TXT_DIR = APPDATA_DIR + os.sep + "labelme_ai"

        # 确保标签txt目录存在
        if not os.path.exists(self.LABEL_TXT_DIR):
            os.makedirs(self.LABEL_TXT_DIR, exist_ok=True)

    # UI 主题切换逻辑已抽离到 `UiThemeManager`（见 `labelme/dlcv/ui_theme_manager.py`）
    # https://bbs.dlcv.com.cn/t/topic/590
    # 编辑标签
    def _edit_label(self, value=None):
        # extra 绘制模式下, 也允许编辑标签
        # if not self.canvas.editing():
        #     return
        # extra end

        items = self.labelList.selectedItems()
        if not items:
            logger.warning("No label is selected, so cannot edit label.")
            return

        shape = items[0].shape()

        if len(items) == 1:
            edit_text = True
            edit_flags = True
            edit_group_id = True
            edit_description = True
        else:
            # extra 修复多个标签名称不同时无法批量修改
            # https://bbs.dlcv.com.cn/t/topic/1057
            edit_text = True
            # extra end
            edit_flags = all(item.shape().flags == shape.flags for item in items[1:])
            edit_group_id = all(
                item.shape().group_id == shape.group_id for item in items[1:]
            )
            edit_description = all(
                item.shape().description == shape.description for item in items[1:]
            )

        if not edit_text:
            self.labelDialog.edit.setDisabled(True)
            self.labelDialog.labelList.setDisabled(True)
        if not edit_flags:
            for i in range(self.labelDialog.flagsLayout.count()):
                self.labelDialog.flagsLayout.itemAt(i).setDisabled(True)
        if not edit_group_id:
            self.labelDialog.edit_group_id.setDisabled(True)
        if not edit_description:
            self.labelDialog.editDescription.setDisabled(True)

        text, flags, group_id, description = self.labelDialog.popUp(
            text=shape.label if edit_text else "",
            flags=shape.flags if edit_flags else None,
            group_id=shape.group_id if edit_group_id else None,
            description=shape.description if edit_description else None,
        )

        if not edit_text:
            self.labelDialog.edit.setDisabled(False)
            self.labelDialog.labelList.setDisabled(False)
        if not edit_flags:
            for i in range(self.labelDialog.flagsLayout.count()):
                self.labelDialog.flagsLayout.itemAt(i).setDisabled(False)
        if not edit_group_id:
            self.labelDialog.edit_group_id.setDisabled(False)
        if not edit_description:
            self.labelDialog.editDescription.setDisabled(False)

        if text is None:
            assert flags is None
            assert group_id is None
            assert description is None
            return
        # extra 修复编辑标签后,标签不更新问题
        else:
            self.labelDialog.addLabelHistory(text)
            if self.uniqLabelList.findItemByLabel(text) is None:
                item = self.uniqLabelList.createItemFromLabel(text)
                self.uniqLabelList.addItem(item)
                rgb = self._get_rgb_by_label(text)
                self.uniqLabelList.setItemLabel(item, text, rgb)
        # extra End

        self.canvas.storeShapes()
        for item in items:
            self._update_item(
                item=item,
                text=text if edit_text else None,
                flags=flags if edit_flags else None,
                group_id=group_id if edit_group_id else None,
                description=description if edit_description else None,
            )

    # 选中的标签发生变化
    def labelSelectionChanged(self):
        if self._noSelectionSlot:
            return
        # extra 绘制模式下, 也允许选择shape
        # if self.canvas.editing():
        #     selected_shapes = []
        #     for item in self.labelList.selectedItems():
        #         selected_shapes.append(item.shape())
        #     if selected_shapes:
        #         self.canvas.selectShapes(selected_shapes)
        #     else:
        #         self.canvas.deSelectShape()

        selected_shapes = []
        for item in self.labelList.selectedItems():
            selected_shapes.append(item.shape())
        if selected_shapes:
            self.canvas.selectShapes(selected_shapes)
        else:
            self.canvas.deSelectShape()
        # extra end

    # region 开发者模式
    def _init_dev_mode(self):
        # https://bbs.dlcv.ai/t/topic/195
        action = QtWidgets.QAction(dlcv_tr("开发者模式"), self)
        action.setShortcut("Ctrl+L")
        action.setCheckable(True)
        action.triggered.connect(self.dev_dialog_popup)
        self.addAction(action)

    def dev_dialog_popup(self):
        dialog = QtWidgets.QDialog(self, Qt.WindowCloseButtonHint)
        dialog.setWindowTitle(dlcv_tr("开发者模式"))
        dialog.setFixedSize(400, 300)

        layout = QtWidgets.QVBoxLayout()
        dialog.setLayout(layout)

        label = QtWidgets.QLabel(dlcv_tr("开发者密码"))
        line_edit = QtWidgets.QLineEdit()
        line_edit.setEchoMode(QtWidgets.QLineEdit.Password)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(label)
        top_layout.addWidget(line_edit)
        layout.addLayout(top_layout)

        button = QtWidgets.QPushButton(dlcv_tr("确定"))
        layout.addWidget(button)
        button.clicked.connect(dialog.accept)

        dialog.exec_()
        if line_edit.text() == "dlcv2024":
            self.dev_setting.setValue("is_dev_mode", True)
        else:
            self.dev_setting.setValue("is_dev_mode", False)
            dialog.reject()

    # endregion

    def tutorial(self):
        # url = 'https://github.com/labelmeai/labelme/tree/main/examples/tutorial'
        url = r"https://docs.dlcv.com.cn/labelme/basic_function/"
        # url = "https://bbs.dlcv.com.cn/labelmeai"  # NOQA
        webbrowser.open(url)

    # https://bbs.dlcv.ai/t/topic/89
    # https://bbs.dlcv.ai/t/topic/90

    # 初始化模式动作
    def populateModeActions(self):
        # 移除 [打开文件] 功能
        self.actions.tool = list(self.actions.tool[1:])

        create_action = functools.partial(utils.newAction, self)

        # https://bbs2.dlcv.com.cn/t/topic/1690
        # 顶栏工具条移除：加载标签文件 / 保存标签文件 / Save 按钮
        # - 仅移除“工具条入口”，文件菜单中的保存等能力仍保留
        if self.actions.save in self.actions.tool:
            self.actions.tool.remove(self.actions.save)

        # 工具栏去除上一幅/下一幅、编辑多边形
        for act in (self.actions.openNextImg, self.actions.openPrevImg, self.actions.editMode):
            if act in self.actions.tool:
                self.actions.tool.remove(act)

        # https://bbs2.dlcv.com.cn/t/topic/1690
        # 将「AI Mask Model」从工具条移除（改到右下角设置面板）
        old_ai_combo = getattr(self, "_selectAiModelComboBox", None)

        def _is_ai_mask_model_action(act) -> bool:
            if not isinstance(act, QtWidgets.QWidgetAction):
                return False
            w = act.defaultWidget()
            if w is None:
                return False
            if old_ai_combo is not None:
                combo = w.findChild(QtWidgets.QComboBox)
                if combo is old_ai_combo:
                    return True
            for lbl in w.findChildren(QtWidgets.QLabel):
                if "AI Mask Model" in lbl.text():
                    return True
            return False

        self.actions.tool = [a for a in self.actions.tool if not _is_ai_mask_model_action(a)]

        # https://bbs.dlcv.com.cn/t/topic/1050
        # 刷新功能
        def refresh():
            self.fileListWidget.update_state()

        self.action_refresh = utils.newAction(
            self,
            dlcv_tr("刷新(F5)"),
            refresh,
            "F5",
            "refresh",
            dlcv_tr("刷新文件夹"),
        )
        self.addAction(self.action_refresh)
        # 放在「打开目录」之后
        self.actions.tool.insert(1, self.action_refresh)

        # 创建AI多边形
        ai_polygon_mode = self.actions.createAiPolygonMode
        ai_polygon_mode.setIconText(
            ai_polygon_mode.text() + f"({ai_polygon_mode.shortcut().toString()})"
        )

        # 创建多边形
        createMode = self.actions.createMode
        # 设置按钮提示文本
        createMode.setIconText(
            createMode.text() + f"({createMode.shortcut().toString()})"
        )

        # 创建矩形框
        createRectangleMode = self.actions.createRectangleMode
        # 设置按钮提示文本
        createRectangleMode.setIconText(
            createRectangleMode.text()
            + f"({createRectangleMode.shortcut().toString()})"
        )

        # 将创建相关动作插入到合适位置：AI多边形 -> 多边形 -> 矩形 -> 旋转框
        try:
            create_mode_idx = self.actions.tool.index(self.actions.createMode)
            self.actions.tool.insert(create_mode_idx, self.actions.createAiPolygonMode)
            # createMode 的位置可能变化，重新获取
            create_mode_idx = self.actions.tool.index(self.actions.createMode)
            self.actions.tool.insert(create_mode_idx + 1, self.actions.createRectangleMode)
        except ValueError:
            self.actions.tool.append(self.actions.createAiPolygonMode)
            self.actions.tool.append(self.actions.createRectangleMode)

        # 创建旋转框
        createRotationMode = create_action(
            dlcv_tr("创建旋转框"),
            lambda: self.toggleDrawMode(False, createMode="rotation"),
            "R",  # 快捷键
            "objects",
            dlcv_tr("开始绘制旋转框 (R)"),
            enabled=False,
        )
        createRotationMode.setIconText(
            createRotationMode.text() + f"({createRotationMode.shortcut().toString()})"
        )
        self.actions.createRotationMode = createRotationMode

        # 未加载图像时，旋转框创建应不可用；加载图像后随 toggleActions(True) 自动启用
        if hasattr(self.actions, "onLoadActive") and (
            self.actions.createRotationMode not in self.actions.onLoadActive
        ):
            self.actions.onLoadActive = tuple(self.actions.onLoadActive) + (
                self.actions.createRotationMode,
            )
        try:
            rect_idx = self.actions.tool.index(self.actions.createRectangleMode)
            self.actions.tool.insert(rect_idx + 1, self.actions.createRotationMode)
        except ValueError:
            self.actions.tool.append(self.actions.createRotationMode)

        # 同时也插入到画布右键菜单中
        if self.actions.createRotationMode not in self.actions.menu:
            # 在菜单最顶部插入创建旋转框
            self.actions.menu = list(self.actions.menu)
            self.actions.menu.insert(2, self.actions.createRotationMode)

        # 亮度对比度禁用
        # https://bbs.dlcv.ai/t/topic/328
        self.actions.brightnessContrast.setVisible(False)

        # dlcv_ai_action
        self._init_dlcv_ai_widget()

        # # https://bbs.dlcv.ai/t/topic/167
        # 移除 [创建 AI 蒙版] 功能
        self.actions.menu = list(self.actions.menu)
        self.actions.menu = self.actions.menu[0:7] + self.actions.menu[8:]

        # https://bbs.dlcv.ai/t/topic/167
        super().populateModeActions()
        self.menus.edit.clear()
        actions = (
            self.actions.createMode,
            self.actions.createRectangleMode,
            self.actions.createRotationMode,
            self.actions.createCircleMode,
            self.actions.createLineMode,
            self.actions.createPointMode,
            self.actions.createLineStripMode,
            self.actions.createAiPolygonMode,
            self.actions.createAiMaskMode,
            self.actions.editMode,
        )
        utils.addActions(self.menus.edit, actions + self.actions.editMenu)

        # 添加查看属性动作
        self.actions.action_view_shape_attr = QtWidgets.QAction(dlcv_tr("查看属性"), self)
        self.actions.action_view_shape_attr.triggered.connect(self.display_shape_attr)
        self.addAction(self.actions.action_view_shape_attr)
        self.actions.menu = list(self.actions.menu)

        # 添加分割线
        self.actions.menu.append(None)
        self.actions.menu.append(self.actions.action_view_shape_attr)

        # 刷新右键菜单
        self.canvas.menus[0].clear()

        utils.addActions(self.canvas.menus[0], self.actions.menu)
        # ------------ 查看属性 end ------------

    def tr(self,*args,**kwargs):
        dlcv_tr('测试')
        return super().tr(*args,**kwargs)

    # 新增设置菜单
    def _init_setting_menu(self):
        # 在菜单栏添加设置菜单选项
        self.menus.setting = self.menu(
            "系统设置(System Settings)"
        )

        # region
        # 语言子菜单
        self.menus.setting_lang = self.menus.setting.addMenu(dlcv_tr("语言(Language)")
        )
        lang_group = QtWidgets.QActionGroup(self)
        lang_group.setExclusive(True)

        self.actions.lang_zh = QtWidgets.QAction("简体中文", self)
        self.actions.lang_zh.setCheckable(True)
        self.actions.lang_zh.setData("zh_CN")
        self.actions.lang_en = QtWidgets.QAction("English", self)
        self.actions.lang_en.setCheckable(True)
        self.actions.lang_en.setData("en_US")

        lang_group.addAction(self.actions.lang_zh)
        lang_group.addAction(self.actions.lang_en)
        self.menus.setting_lang.addAction(self.actions.lang_zh)
        self.menus.setting_lang.addAction(self.actions.lang_en)

        current_lang = dlcv_tr.get_lang()
        if current_lang == "en_US":
            self.actions.lang_en.setChecked(True)
        else:
            self.actions.lang_zh.setChecked(True)

        lang_group.triggered.connect(lambda act: self._on_change_language(act.data()))
        # endregion

        # region
        # 字体大小子菜单（应用全局 UI 字体大小）
        self.menus.setting_font = self.menus.setting.addMenu(
            dlcv_tr("字体大小")
        )
        font_group = QtWidgets.QActionGroup(self)
        font_group.setExclusive(True)
        font_sizes = [8, 9, 10, 12, 14, 16, 18, 20]

        # 当前字号：优先读取设置；否则读取当前应用字体
        try:
            current_font_size = self.settings.value(
                "ui/font_point_size", None, type=int
            )
        except Exception:
            # 默认为10
            current_font_size = 10
        print(f'@@@当前字体：{current_font_size}')

        self.actions.font_size_actions = []
        for size in font_sizes:
            act = QtWidgets.QAction(f"{size}", self)
            act.setCheckable(True)
            act.setData(size)
            if current_font_size == size:
                act.setChecked(True)
            font_group.addAction(act)
            self.menus.setting_font.addAction(act)
            self.actions.font_size_actions.append(act)

        font_group.triggered.connect(
            lambda act: self._on_change_ui_font_point_size(int(act.data()))
        )
        # endregion

        # region
        # 界面风格切换（独立组件负责安装与切换）
        try:
            if hasattr(self, "ui_theme_manager") and self.ui_theme_manager is not None:
                self.ui_theme_manager.install_to_setting_menu(self.menus.setting)
        except Exception:
            logger.error(traceback.format_exc())
        # endregion

        # 尾部分隔线（预留未来扩展）
        self.menus.setting.addSeparator()

    def _on_change_language(self, lang_code: str):
        lang_code = lang_code or "zh_CN"
        # 保存到设置
        try:
            self.settings.setValue("ui/language", lang_code)
        except Exception:
            QtCore.QSettings("labelme", "labelme").setValue("ui/language", lang_code)
        
        cn_lang_title = '语言设置'
        cn_lang_info = '语言已更改，请重启软件以应用修改。'
    
        en_lang_title = 'Language Setting'
        en_lang_info = 'Language changed. Please restart the software to apply the modification.'
        
        # 通知用户
        notification(
            cn_lang_title,
            cn_lang_info,
            ToastPreset.WARNING,
            8000
        )
        
        notification(
            en_lang_title,
            en_lang_info,
            ToastPreset.WARNING,
            8000
        )
        
        # 弹窗询问是否重启软件
        # reply = QtWidgets.QMessageBox.question(
        #     self, 
        #     dlcv_tr("重启软件"), 
        #     dlcv_tr("是否重启软件以应用修改？"), 
        #     QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
        #     QtWidgets.QMessageBox.No
        # )
        
        # if reply == QtWidgets.QMessageBox.Yes:
        #     # 先确保设置写入磁盘
        #     try:
        #         self.settings.sync()
        #     except Exception:
        #         pass
        #     # 使用当前可执行文件与参数重新启动进程（兼容开发与打包环境）
        #     program = QtCore.QCoreApplication.applicationFilePath()
        #     arguments = QtWidgets.QApplication.arguments()
        #     try:
        #         QtCore.QProcess.startDetached(program, arguments)
        #     except Exception:
        #         # 兜底：在极端情况下使用 sys.executable 重启
        #         try:
        #             QtCore.QProcess.startDetached(sys.executable, sys.argv[1:])
        #         except Exception:
        #             pass
        #     # 退出当前实例
        #     QtWidgets.QApplication.quit()

    def _on_change_ui_font_point_size(self, point_size: int):
        # 应用到全局 UI 字体
        app = QtWidgets.QApplication.instance()
        if app is not None and isinstance(point_size, int) and point_size > 0:
            font = app.font()
            font.setPointSize(point_size)
            app.setFont(font)
            try:
                if hasattr(self, "ui_theme_manager") and self.ui_theme_manager is not None:
                    self.ui_theme_manager.on_app_font_changed()
            except Exception:
                logger.error(traceback.format_exc())
        try:
            self.settings.setValue("ui/font_point_size", int(point_size))
        except Exception:
            pass
        notification(
            dlcv_tr("字体大小"),
            dlcv_tr(f"{dlcv_tr('已设置为')} {point_size}"),
            ToastPreset.INFORMATION,
        )

    # https://bbs.dlcv.ai/t/topic/94
    def closeEvent(self, event):
        super().closeEvent(event)
        self.settings.setValue("lastOpenDir", self.lastOpenDir)

        # extra 保存设置
        # 保存store里面的设置
        setting_store = {
            "display_shape_label": STORE.canvas_display_shape_label,
            "shape_label_font_size": STORE.canvas_shape_label_font_size,  # 新增：保存标签字体大小
            "highlight_start_point": STORE.canvas_highlight_start_point,
            "convert_img_to_gray": STORE.convert_img_to_gray,
            "canvas_display_rotation_arrow": STORE.canvas_display_rotation_arrow,
            "canvas_brush_fill_region": STORE.canvas_brush_fill_region,
            "canvas_brush_enabled": STORE.canvas_brush_enabled,  # 新增：保存画笔标注设置
            "canvas_brush_size": STORE.canvas_brush_size,  # 新增：保存画笔大小
            "canvas_points_to_crosshair": STORE.canvas_points_to_crosshair,  # 新增：保存点转十字设置
            "scale_option": self.parameter.child(
                "other_setting", "scale_option"
            ).value(),
            "ai_polygon_simplify_epsilon": self.parameter.child(
                "label_setting", "ai_polygon_simplify_epsilon"
            ).value(),
        }
        self.settings.setValue("setting_store", setting_store)
        self.__store_splitter_sizes()
        # extra End

    # 加载标签文件
    def load_label_txt_action_callback(self):
        file_dialog = QtWidgets.QFileDialog(self)
        file_dialog.setWindowTitle(dlcv_tr("选择要加载的标签txt文件"))
        file_dialog.setDirectory(self.LABEL_TXT_DIR)
        file_dialog.setNameFilter(dlcv_tr("标签文件 (*.txt)"))
        file_dialog.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        if file_dialog.exec_() == QtWidgets.QFileDialog.Accepted:
            file_path = file_dialog.selectedFiles()[0]
            self._load_label_txt(file_path)

    def _load_label_txt(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            all_labels = [line.strip() for line in lines if line.strip()]

            if not all_labels:
                notification(
                    dlcv_tr("标签文件为空"),
                    dlcv_tr("该标签文件没有任何标签。"),
                    ToastPreset.INFORMATION,
                )
                return

            loaded_count = 0
            for label in all_labels:
                if self.uniqLabelList.findItemByLabel(label) is None:
                    item = self.uniqLabelList.createItemFromLabel(label)
                    self.uniqLabelList.addItem(item)
                    rgb = self._get_rgb_by_label(label)
                    self.uniqLabelList.setItemLabel(item, label, rgb)
                    loaded_count += 1

            if loaded_count > 0:
                notification(
                    dlcv_tr("标签加载完成"),
                    dlcv_tr("成功加载 {count} 个新标签。").format(count=loaded_count),
                    ToastPreset.SUCCESS,
                )
            else:
                notification(
                    dlcv_tr("标签加载完成"),
                    dlcv_tr("未发现新标签，所有标签已存在。"),
                    ToastPreset.INFORMATION,
                )
        except Exception as e:
            notification(dlcv_tr("加载标签文件失败"), str(e), ToastPreset.ERROR)

    # 新增保存标签文件控件
    def save_label_txt_file(self):
        # 弹出文件名输入框，让用户指定文件名
        file_name, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, dlcv_tr("保存标签文件"), self.LABEL_TXT_DIR, dlcv_tr("标签文件 (*.txt)")
        )
        if file_name:
            self._save_label_txt(file_name)

    # 缓存标签列表
    def _save_label_txt(self, filename):
        """
        将当前唯一标签列表（uniqLabelList）保存为txt文件。
        文件名由用户指定，保存在 LABEL_TXT_DIR 目录下。
        :param filename: 用户指定的文件名（不带路径，可带或不带.txt后缀）
        """
        label_set = set()
        for i in range(self.uniqLabelList.count()):
            item = self.uniqLabelList.item(i)
            label = item.data(Qt.UserRole) if hasattr(item, "data") else item.text()
            label_set.add(label)
        # 优化文件名后缀处理，确保只保存为txt文件
        filename = str(filename).strip()
        suffix = Path(filename).suffix.lower()
        if suffix != ".txt":
            # 去除原有后缀，强制添加.txt
            filename = Path(filename).stem + ".txt"
        file_path = os.path.join(self.LABEL_TXT_DIR, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            for label in sorted(label_set):
                f.write(label + "\n")
        logger.info(f"保存标签到 {file_path}")
        return file_path

    # 初始化修改颜色action并添加到右键菜单
    def _init_shape_color_action(self):
        """初始化修改颜色功能"""
        from labelme.dlcv.utils.change_shape_color import init_change_color_action

        init_change_color_action(self)

    # ------------ Ctrl + C 触发函数 复制图片 ------------
    def copySelectedShape(self):
        """
        复制当前图片。
        """
        self.copy_image_to_clipboard()

    # 当选中形状变化时
    def shapeSelectionChanged(self, selected_shapes):
        super().shapeSelectionChanged(selected_shapes)
        self.actions.copy.setEnabled(True)
        # 使用保存的action对象，而不是方法
        if hasattr(self.actions, "changeColor"):
            n_selected = len(selected_shapes)
            self.actions.changeColor.setEnabled(n_selected > 0)

    # 复制图片到剪贴板
    def copy_image_to_clipboard(self):
        """复制当前图片到剪贴板"""
        # 获取当前画布显示的图片路径
        file_path = getattr(self, "imagePath", None)

        if not file_path:
            notification(
                dlcv_tr("提示"),
                dlcv_tr("请先选中一张图片。"),
                ToastPreset.WARNING,
            )
            return

        try:
            copy_file_to_clipboard(file_path)
            notification(
                dlcv_tr("复制成功"),
                dlcv_tr("图片已复制到剪贴板，可直接粘贴为文件。"),
                ToastPreset.SUCCESS,
            )
        except Exception as e:
            notification(
                dlcv_tr("复制失败"),
                str(e),
                ToastPreset.ERROR,
            )

        # ------------ Ctrl + C 触发函数 end ------------

    # 复制形状到剪贴板  ctrl+d/ctrl+v
    def duplicateSelectedShape(self):
        """重写父类方法：复制选中的形状到剪贴板"""
        if not self.canvas.selectedShapes:
            notification(dlcv_tr("提示"), dlcv_tr("请先选中要复制的形状"), ToastPreset.WARNING)
            return

        try:
            # 将选中的形状转换为可序列化的字典数据
            shapes_data = []
            for shape in self.canvas.selectedShapes:
                shape_data = self.format_shape_for_clipboard(shape)
                shapes_data.append(shape_data)

            # 记录源图像路径
            source_image_path = self.filename
            logger.info(f"=== DEBUG: 记录源图像路径: {source_image_path} ===")

            # 复制到剪贴板
            from labelme.dlcv.widget.clipboard import copy_shapes_to_clipboard

            copy_shapes_to_clipboard(shapes_data, source_image_path)

            # 启用粘贴动作
            self.actions.paste.setEnabled(True)

            notification(
                dlcv_tr("复制成功"),
                dlcv_tr("已复制 {count} 个形状到剪贴板").format(count=len(shapes_data)),
                ToastPreset.SUCCESS,
            )

        except Exception as e:
            notification(dlcv_tr("复制失败"), str(e), ToastPreset.ERROR)

    # 将形状对象格式化为可序列化的字典
    def format_shape_for_clipboard(self, shape):
        """将形状对象格式化为可序列化的字典"""

        # 创建新的数据字典，不从other_data复制，避免冲突
        data = {}
        points_data = [(p.x(), p.y()) for p in shape.points]

        data.update(
            {
                "label": shape.label,
                "points": points_data,
                "group_id": shape.group_id,
                "description": shape.description,
                "shape_type": shape.shape_type,
                "flags": shape.flags,
                "mask": None if shape.mask is None else shape.mask.tolist(),
            }
        )

        # 如果是旋转框，添加direction属性
        if shape.shape_type == "rotation":
            data["direction"] = getattr(shape, "direction", 0.0)
        return data

    # 从形状数据创建Shape对象
    def create_shape_from_data(self, shape_data):
        """从形状数据创建Shape对象"""
        try:
            from labelme.dlcv.shape import Shape
            from PyQt5 import QtCore

            # 创建Shape对象
            shape = Shape()

            # 设置基本属性
            shape.label = shape_data.get("label", "")
            shape.shape_type = shape_data.get("shape_type", "polygon")
            shape.group_id = shape_data.get("group_id")
            shape.description = shape_data.get("description", "")
            shape.flags = shape_data.get("flags", {})

            # 设置点坐标
            points = shape_data.get("points", [])
            for point in points:
                shape.addPoint(QtCore.QPointF(point[0], point[1]))

            # 对于多边形等需要闭合的形状，手动调用close()
            if shape.shape_type in ["polygon", "linestrip"] and len(points) > 0:
                shape.close()

            # 设置mask
            mask_data = shape_data.get("mask")
            if mask_data is not None:
                import numpy as np

                shape.mask = np.array(mask_data)

            # 如果是旋转框，设置direction属性
            if shape.shape_type == "rotation":
                shape.direction = shape_data.get("direction", 0.0)

            return shape

        except Exception as e:
            import traceback

            traceback.print_exc()
            raise

    # 为形状添加偏移，避免与原形状重合
    def add_offset_to_shape(self, shape):
        """为形状添加偏移，避免与原形状重合"""

        # 偏移量
        offset_x, offset_y = 20, 20

        # 计算形状的边界
        min_x = min(p.x() for p in shape.points)
        max_shape_x = max(p.x() for p in shape.points)
        min_y = min(p.y() for p in shape.points)
        max_shape_y = max(p.y() for p in shape.points)

        max_x = self.image.width() - 0.001
        max_y = self.image.height() - 0.001

        # 检查偏移后是否会出界
        if max_shape_x + offset_x > max_x:
            offset_x = max(0, max_x - max_shape_x - 10)
        if max_shape_y + offset_y > max_y:
            offset_y = max(0, max_y - max_shape_y - 10)

        # 如果偏移太小，尝试向左上偏移
        if offset_x < 10:
            if min_x - 20 >= 0:
                offset_x = -20
            else:
                offset_x = 0
        if offset_y < 10:
            if min_y - 20 >= 0:
                offset_y = -20
            else:
                offset_y = 0

        # 应用偏移
        for point in shape.points:
            new_x = point.x() + offset_x
            new_y = point.y() + offset_y
            # 确保不超出边界
            new_x = max(0, min(new_x, max_x))
            new_y = max(0, min(new_y, max_y))
            point.setX(new_x)
            point.setY(new_y)

        # 偏移后直接检查边界并自动调整
        self.check_and_adjust_shape_bounds(shape)

    # 检查形状是否超出当前图像边界，如果超出则调整
    def check_and_adjust_shape_bounds(self, shape):
        """检查形状是否超出当前图像边界，如果超出则调整"""
        # 计算形状的边界
        min_x = min(p.x() for p in shape.points)
        max_shape_x = max(p.x() for p in shape.points)
        min_y = min(p.y() for p in shape.points)
        max_shape_y = max(p.y() for p in shape.points)

        # 检查形状是否超出当前图像边界
        max_x = self.image.width() - 0.001
        max_y = self.image.height() - 0.001

        if max_shape_x > max_x or max_shape_y > max_y or min_x < 0 or min_y < 0:
            # 如果形状超出边界，给出警告并调整到边界内
            notification(
                dlcv_tr("警告"),
                dlcv_tr("粘贴的形状超出当前图像边界，已自动调整"),
                ToastPreset.WARNING,
            )

            # 计算缩放比例以适应新图像
            scale_x = max_x / max_shape_x if max_shape_x > max_x else 1.0
            scale_y = max_y / max_shape_y if max_shape_y > max_y else 1.0
            scale = min(scale_x, scale_y, 1.0)  # 不放大，只缩小

            # 应用缩放
            for point in shape.points:
                new_x = point.x() * scale
                new_y = point.y() * scale
                # 确保不超出边界
                new_x = max(0, min(new_x, max_x))
                new_y = max(0, min(new_y, max_y))
                point.setX(new_x)
                point.setY(new_y)

    def pasteSelectedShape(self):
        """从剪贴板粘贴形状或图像"""
        try:
            # 首先尝试从剪贴板读取形状数据
            from labelme.dlcv.widget.clipboard import paste_shapes_from_clipboard

            shapes_data = paste_shapes_from_clipboard()

            if shapes_data is not None:
                logger.info(f"=== DEBUG: 当前图像路径: {self.filename} ===")

                # 将形状数据转换为Shape对象并添加偏移
                shapes = []
                for i, shape_data in enumerate(shapes_data):
                    shape = self.create_shape_from_data(shape_data)

                    # 检查是否需要应用偏移（只在同一张图片上粘贴时应用偏移）
                    source_image_path = shape_data.get("source_image_path")
                    current_image_path = self.filename

                    if source_image_path == current_image_path:
                        logger.info(f"=== DEBUG: 在同一张图片上粘贴，应用偏移 ===")
                        # 添加偏移以避免与原形状重合
                        self.add_offset_to_shape(shape)
                    else:
                        logger.info(
                            f"=== DEBUG: 在不同图片上粘贴，不应用偏移，保持原始坐标 ==="
                        )
                        # 检查形状是否超出当前图像边界，如果超出则调整
                        self.check_and_adjust_shape_bounds(shape)

                    shapes.append(shape)

                # 加载形状到画布
                self.loadShapes(shapes, replace=False)
                self.setDirty()

                # 粘贴完成后，立即选中
                self.canvas.selectShapes(shapes)

                notification(
                    dlcv_tr("粘贴成功"),
                    dlcv_tr("已粘贴 {count} 个形状").format(count=len(shapes)),
                    ToastPreset.SUCCESS,
                )
                return

            # 如果没有形状数据，尝试粘贴图像
            try:
                # 调用父类的粘贴图像功能
                super().pasteSelectedShape()
                return
            except Exception as e:
                pass

            # 如果图像粘贴也失败，尝试使用原有的_copied_shapes机制
            if not self._copied_shapes:
                notification(
                    dlcv_tr("提示"), dlcv_tr("剪贴板中没有可粘贴的内容"), ToastPreset.WARNING
                )
                return

            nee_copy_shape = []
            for copy_shape in self._copied_shapes:
                for shape in self.canvas.shapes:
                    if copy_shape.points == shape.points:
                        nee_copy_shape.append(shape)

            if nee_copy_shape:
                self.canvas.selectShapes(nee_copy_shape)
                self.duplicateSelectedShape()
            else:
                self.loadShapes(self._copied_shapes, replace=False)
                self.setDirty()

        except Exception as e:
            import traceback

            traceback.print_exc()
            notification(dlcv_tr("粘贴失败"), str(e), ToastPreset.ERROR)

    def fileSelectionChanged(self):
        if not self.is_all_shapes_valid():
            # 弹窗询问是否切换图片
            reply = QtWidgets.QMessageBox.question(
                self,
                "存在不合法多边形",
                "存在不合法多边形,是否切换图片?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.No:
                return
        return super().fileSelectionChanged()

    # https://bbs.dlcv.ai/t/topic/99
    # 保存 json 的函数： 自动保存标签
    def saveLabels(self, filename: str):
        """filename: json 文件路径"""
        # extra 保存 3d 或 2.5d json
        if self.is_3d or self.is_2_5d:
            filename = self.getLabelFile()

        lf = LabelFile()

        def format_shape(s):
            data = s.other_data.copy()
            data.update(
                dict(
                    label=s.label.encode("utf-8") if PY2 else s.label,
                    points=[(p.x(), p.y()) for p in s.points],
                    group_id=s.group_id,
                    description=s.description,
                    shape_type=s.shape_type,
                    flags=s.flags,
                    mask=(
                        None
                        if s.mask is None
                        else utils.img_arr_to_b64(s.mask.astype(np.uint8))
                    ),
                )
            )
            # 如果是旋转框，保存direction属性
            if s.shape_type == "rotation":
                data["direction"] = s.direction
            return data

        # extra 修正多边形，防止越界
        for t_shape in self.canvas.shapes:
            self.fix_shape(t_shape)

        shapes = [format_shape(item.shape()) for item in self.labelList]

        flags = {}
        for i in range(self.flag_widget.count()):
            item = self.flag_widget.item(i)
            key = item.text()
            flag = item.checkState(0) == Qt.Checked
            flags[key] = flag

        # extra 如果当前 shapes 为空, 并且 flags 没有 true, 则删除标签文件
        if not shapes and not any(flags.values()):
            label_file = self.getLabelFile()
            if osp.exists(label_file):
                os.remove(label_file)
                items = self.fileListWidget.findItems(self.filename, Qt.MatchContains)
                for item in items:
                    item.setCheckState(Qt.Unchecked)
                logger.info(f"删除{label_file}")
            # 如果是2.5d模式，则需要更新所有使用该JSON的图片的勾选状态
            if self.is_2_5d:
                # 从映射中查找完整路径
                json_name = os.path.basename(label_file)
                json_dir = os.path.dirname(label_file)  # 获取JSON文件所在目录
                proj_manager = self.proj_manager.o2_5d_manager
                # 只查找同一目录下使用该JSON的完整路径
                img_paths = [img_path for img_path, json_file in proj_manager._file_to_json.items()
                            if json_file == json_name and os.path.dirname(img_path) == json_dir]
                for img_path in img_paths:
                    # 标准化路径格式
                    img_path = str(Path(img_path).absolute().as_posix())
                    items = self.fileListWidget.findItems(img_path, Qt.MatchExactly)
                    for item in items:
                        item.setCheckState(Qt.Unchecked)
            # extra End
            # 实时更新统计信息
            if hasattr(self, "label_count_dock"):
                self.label_count_dock.count_labels_in_file([], {})
            return True

        # 不需要保存 False 的 flag
        flags = {k: v for k, v in flags.items() if v}
        # extra End

        try:
            imagePath = osp.relpath(self.imagePath, osp.dirname(filename))
            imageData = self.imageData if self._config["store_data"] else None
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))

            # extra 统一使用get_img_name_list接口管理图片名列表
            img_name_list = self.proj_manager.get_img_name_list(self.filename)
            if img_name_list:
                # 确保otherData存在
                if self.otherData is None:
                    self.otherData = {}
                self.otherData["img_name_list"] = img_name_list
            # extra End

            lf.save(
                filename=filename,
                shapes=shapes,
                imagePath=imagePath,
                imageData=imageData,
                imageHeight=self.image.height(),
                imageWidth=self.image.width(),
                otherData=self.otherData,
                flags=flags,
            )
            self.labelFile = lf
            # extra 保存成功后, self.labelFile 里的数据会被清空, 所以需要重新加载,防止别的地方调用 self.labelFile 时出错
            self.labelFile.load(filename)
            # extra End

            # 保存标注时，设置文件列表的勾选状态
            # extra 2.5D模式：需要更新所有使用该JSON的图片的勾选状态
            if self.is_2_5d:
                # 从otherData中获取图片列表
                img_name_list = self.labelFile.otherData.get('img_name_list', [])
                if img_name_list:
                    # 从映射中查找完整路径
                    json_name = os.path.basename(filename)
                    json_dir = os.path.dirname(filename)  # 获取JSON文件所在目录
                    proj_manager = self.proj_manager.o2_5d_manager
                    # 只查找同一目录下使用该JSON的完整路径
                    img_paths = [img_path for img_path, json_file in proj_manager._file_to_json.items()
                                if json_file == json_name and os.path.dirname(img_path) == json_dir]
                    for img_path in img_paths:
                        # 标准化路径格式
                        img_path = str(Path(img_path).absolute().as_posix())
                        items = self.fileListWidget.findItems(img_path, Qt.MatchExactly)
                        for item in items:
                            item.setCheckState(Qt.Checked)
                else:
                    # 如果没有图片列表 使用当前图片
                    items = self.fileListWidget.findItems(self.filename, Qt.MatchExactly)
                    if len(items) == 0:
                        items = self.fileListWidget.findItems(self.filename, Qt.MatchExactly)
                    if len(items) > 0:
                        for item in items:
                            item.setCheckState(Qt.Unchecked)
            else:
                items = self.fileListWidget.findItems(self.filename, Qt.MatchExactly)
                if len(items) == 0:
                    items = self.fileListWidget.findItems(self.filename, Qt.MatchExactly)
                if len(items) > 0:
                    for item in items:
                        item.setCheckState(Qt.Checked)
            # extra End

            # 实时更新统计信息
            if hasattr(self, "label_count_dock"):
                self.label_count_dock.count_labels_in_file(self.canvas.shapes, flags)

            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.errorMessage(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    # https://bbs.dlcv.ai/t/topic/99
    def deleteSelectedShape(self):
        if len(self.flag_widget.selectedItems()) > 0:
            self.flag_widget.takeItem(self.flag_widget.currentRow())
            self.setDirty()
            return
        else:
            self.remLabels(self.canvas.deleteSelected())
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    # 防止加载标签失败导致程序崩溃
    def loadLabels(self, shapes: dict):
        try:
            super().loadLabels(shapes)
        except:
            error_msg = traceback.format_exc()
            logger.error(error_msg)
            notification(
                "加载标签失败",
                f"请检查标签文件是否正确,当前标签文件: {self.labelFile.filename}",
                ToastPreset.ERROR,
            )

    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        # 在弹窗前先处理AI多边形简化
        if self.canvas.createMode == "ai_polygon" and self.canvas.shapes:
            last_shape = self.canvas.shapes[-1]
            if last_shape.shape_type == "polygon" and len(last_shape.points) > 3:
                logger.info(f"简化前点数: {len(last_shape.points)}")
                self.simplifyShapePoints(last_shape)
                logger.info(f"简化后点数: {len(last_shape.points)}")

        items = self.uniqLabelList.selectedItems()
        text = None

        if items:
            text = items[0].data(Qt.UserRole)
        flags = {}
        group_id = None
        description = ""
        if self._config["display_label_popup"] or not text:
            previous_text = self.labelDialog.edit.text()
            text, flags, group_id, description = self.labelDialog.popUp(text)
            if not text:
                self.labelDialog.edit.setText(previous_text)

        if text and not self.validateLabel(text):
            self.errorMessage(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            text = ""
        if text:
            self.labelList.clearSelection()
            shape = self.canvas.setLastLabel(text, flags)
            shape.group_id = group_id
            shape.description = description

            # extra AI自动标注，有可能出现不合法的多边形
            if self.canvas.createMode == "ai_polygon":
                shape = self.fix_shape(shape)
            self.addLabel(shape)
            self.actions.editMode.setEnabled(True)
            self.actions.undoLastPoint.setEnabled(False)
            self.actions.undo.setEnabled(True)
            self.setDirty()

            # https://bbs2.dlcv.com.cn/t/topic/1048/3
            # 保存 label.txt
            label_txt_path = Path(self.lastOpenDir) / "label.txt"
            self._save_label_txt(label_txt_path)
            # extra end
        else:
            self._cancel_shape_creation()

    def _cancel_shape_creation(self):
        """彻底清理取消标签输入后的残留状态"""
        try:
            # 恢复绘图状态
            self.canvas.undoLastLine()
            self.canvas.shapesBackups.pop()
        except:
            pass

        # 强制清除所有绘制状态
        if STORE.canvas_brush_enabled:
            self.canvas.cancelBrushDrawing()

            # 重置画布状态
            self.canvas.current = None
            self.canvas.line.points = []
            self.canvas.line.point_labels = []
            self.canvas.drawingPolygon.emit(False)

            # 切换到编辑模式 - 使用toggleDrawMode确保完全切换UI状态
            self.toggleDrawMode(edit=True)

            # 强制刷新界面
            self.canvas.update()

    def loadShapes(self, shapes: [Shape], replace=True):
        # extra 修复 points 少于 3 个点, 加载标签失败, 导致程序崩溃
        fix_shapes = []
        for shape in shapes:
            points_num = len(shape.points)
            if points_num < 3 and shape.shape_type == ShapeType.POLYGON:
                logger.warning(f"多边形: {shape.label} 小于 3 个点, 已删除")
                continue

            # 如果是旋转框，确保有direction属性
            if shape.shape_type == ShapeType.ROTATION and not hasattr(
                shape, "direction"
            ):
                shape.direction = 0.0

            shape = self.fix_shape(shape)
            fix_shapes.append(shape)

        super().loadShapes(fix_shapes, replace)
        if len(fix_shapes) != len(shapes):
            self.setDirty()

    def undoShapeEdit(self):
        super().undoShapeEdit()
        self.setDirty()

    # https://github.com/wkentaro/labelme/pull/1470
    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
        self.actions.createAiPolygonMode.setEnabled(True)
        self.actions.createAiMaskMode.setEnabled(True)
        title = __appname__
        if self.filename is not None:
            # extra 添加文件进度
            file_index = self.fileListWidget.currentRow()
            title = f"{title} - {self.filename} ({file_index + 1}/{self.fileListWidget.count()})"
            # extra end
        self.setWindowTitle(title)

        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def getLabelFile(self) -> str:
        try:
            assert self.filename is not None

            # 2.5D模式：使用公共前缀的JSON文件名来获取json路径
            return self.proj_manager.get_json_path(self.filename)
        except:
            notification(
                title=dlcv_tr("获取标签文件失败"),
                text=dlcv_tr("代码不应该运行到这里"),
                preset=ToastPreset.ERROR,
            )
            raise Exception(dlcv_tr("获取标签文件失败"))

    def get_vertical_scrollbar(self):
        return self.scrollBars[Qt.Vertical]

    def get_horizontal_scrollbar(self):
        return self.scrollBars[Qt.Horizontal]

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        # changing fileListWidget loads file
        # if filename in self.imageList and (self.fileListWidget.currentRow()
        #                                    != self.imageList.index(filename)):
        #     self.fileListWidget.setCurrentRow(self.imageList.index(filename))
        #     self.fileListWidget.repaint()
        #     return

        # changing fileListWidget loads file
        if filename in self.imageList and (
            self.fileListWidget.currentRow() != self.imageList.index(filename)
        ):
            self.fileListWidget.setCurrentRow(self.imageList.index(filename))
            self.fileListWidget.repaint()
            # return 不需要 return

        """保存当前图片的滚动条百分比"""
        hbar = self.get_horizontal_scrollbar()
        vbar = self.get_vertical_scrollbar()
        x_percent = hbar.value() / hbar.maximum() if hbar.maximum() > 0 else 0.0
        y_percent = vbar.value() / vbar.maximum() if vbar.maximum() > 0 else 0.0
        last_scroll_percent = (round(x_percent, 3), round(y_percent, 3))

        self.resetState()
        self.canvas.setEnabled(False)
        if filename is None:
            filename = self.settings.value("filename", "")
        filename = str(filename)
        if not QtCore.QFile.exists(filename):
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr("No such file: <b>%s</b>") % filename,
            )
            return False

        # extra 修复加载 json 文件失败,会从文件列表【0】处重新加载
        self.filename = filename
        # extra End

        # assumes same name, but json extension
        self.status(str(self.tr("Loading %s...")) % osp.basename(str(filename)))

        label_file = self.getLabelFile()
        if self.output_dir:
            label_file_without_path = osp.basename(label_file)
            label_file = osp.join(self.output_dir, label_file_without_path)

        # https://bbs.dlcv.ai/t/topic/328
        # extra 弃用 self.imageData
        assert self.imageData is None
        from labelme.utils.image import numpy_to_qimage

        file_path = filename
        if osp.getsize(file_path) <= 0:
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr("文件大小为0"),
            )
            return True

        try:
            if osp.getsize(file_path) < 100000000:
                if isinstance(file_path, str):
                    file_path_encode = file_path.encode("utf-8")
                cv_img = cv2.imdecode(
                    np.fromfile(file_path_encode, dtype=np.uint8),
                    cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH,
                )
            else:
                image = Image.open(f"{file_path}")
                image = np.array(image)
                cv_img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        except:
            notification(
                dlcv_tr("提示"), dlcv_tr("无法打开图片，请检查文件是否已损坏"), ToastPreset.ERROR
            )
            return False

        if cv_img is None:
            notification(
                dlcv_tr("提示"), dlcv_tr("无法打开图片，请检查文件是否已损坏"), ToastPreset.ERROR
            )
            return False

        cv_img = normalize_16b_gray_to_uint8(cv_img)
        if len(cv_img.shape) == 2:
            cv_rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB)
        else:
            cv_rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

        if STORE.convert_img_to_gray:
            cv_rgb_img = cv2.cvtColor(cv_rgb_img, cv2.COLOR_RGB2GRAY)
            cv_rgb_img = cv2.cvtColor(cv_rgb_img, cv2.COLOR_GRAY2RGB)

        image = numpy_to_qimage(cv_rgb_img)
        # extra End

        if image.isNull():
            formats = [
                "*.{}".format(fmt.data().decode())
                for fmt in QtGui.QImageReader.supportedImageFormats()
            ]
            self.errorMessage(
                self.tr("Error opening file"),
                self.tr(
                    "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
                    "Supported image formats: {1}</p>"
                ).format(filename, ",".join(formats)),
            )
            self.status(self.tr("Error reading %s") % filename)
            return False
        self.image = image
        self.filename = filename
        if self._config["keep_prev"]:
            prev_shapes = self.canvas.shapes

        # 2025年8月7日 切换图片后，重置绘制的x,y位置
        self.canvas.offset = QtCore.QPointF(0, 0)
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))

        if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
            try:
                # 从标签文件里加载标签
                self.labelFile = LabelFile(label_file)
            except LabelFileError as e:
                self.errorMessage(
                    self.tr("Error opening file"),
                    self.tr(
                        "<p><b>%s</b></p>"
                        "<p>Make sure <i>%s</i> is a valid label file."
                    )
                    % (e, label_file),
                )
                self.status(self.tr("Error reading %s") % label_file)
                return False
            self.imageData = self.labelFile.imageData
            self.imagePath = osp.join(
                osp.dirname(label_file),
                self.labelFile.imagePath,
            )

            self.otherData = self.labelFile.otherData
        else:
            self.imageData = LabelFile.load_image_file(filename)
            # extra 弃用 self.imageData
            # if self.imageData:
            #     self.imagePath = filename
            self.imagePath = filename
            # extra End
            self.labelFile = None

        flags = {k: False for k in self._config["flags"] or []}
        if self.labelFile:
            self.loadLabels(self.labelFile.shapes)
            # 若有flags，则加载flags
            if self.labelFile.flags is not None:
                flags.update(self.labelFile.flags)

        self.loadFlags(flags)
        if self._config["keep_prev"] and self.noShapes():
            self.loadShapes(prev_shapes, replace=False)
            self.setDirty()
        else:
            self.setClean()
        self.canvas.setEnabled(True)

        # extra 修复缩放问题
        # set zoom values
        # is_initial_load = not self.zoom_values
        # if self.filename in self.zoom_values:
        #     self.zoomMode = self.zoom_values[self.filename][0]
        #     self.setZoom(self.zoom_values[self.filename][1])
        # elif is_initial_load or not self._config["keep_prev_scale"]:
        #     self.adjustScale(initial=True)

        is_initial_load = not self.zoom_values or self.filename not in self.zoom_values

        if self.keep_scale:  # 保持缩放比例
            hbar = self.get_horizontal_scrollbar()
            vbar = self.get_vertical_scrollbar()
            hbar.setValue(int(last_scroll_percent[0] * hbar.maximum()))
            vbar.setValue(int(last_scroll_percent[1] * vbar.maximum()))
        elif not self._config["keep_prev_scale"]:
            self.adjustScale(initial=True)
        elif self.filename in self.zoom_values:
            self.zoomMode = self.zoom_values[self.filename][0]
            self.setZoom(self.zoom_values[self.filename][1])
        elif is_initial_load:
            self.adjustScale(initial=True)
        # extra End

        # set scroll values
        if not self.keep_scale:  # 不知道这段代码有什么用
            for orientation in self.scroll_values:
                if self.filename in self.scroll_values[orientation]:
                    self.setScroll(
                        orientation, self.scroll_values[orientation][self.filename]
                    )
        # set brightness contrast values
        # dialog = BrightnessContrastDialog(
        #     utils.img_data_to_pil(self.imageData),
        #     self.onNewBrightnessContrast,
        #     parent=self,
        # )
        # brightness, contrast = self.brightnessContrast_values.get(
        #     self.filename, (None, None)
        # )
        # if self._config["keep_prev_brightness"] and self.recentFiles:
        #     brightness, _ = self.brightnessContrast_values.get(
        #         self.recentFiles[0], (None, None)
        #     )
        # if self._config["keep_prev_contrast"] and self.recentFiles:
        #     _, contrast = self.brightnessContrast_values.get(
        #         self.recentFiles[0], (None, None)
        #     )
        # if brightness is not None:
        #     dialog.slider_brightness.setValue(brightness)
        # if contrast is not None:
        #     dialog.slider_contrast.setValue(contrast)
        # self.brightnessContrast_values[self.filename] = (brightness, contrast)
        # if brightness is not None or contrast is not None:
        #     dialog.onNewValue(None)

        self.paintCanvas()
        self.addRecentFile(self.filename)
        self.toggleActions(True)
        self.canvas.setFocus()
        self.status(str(self.tr("Loaded %s")) % osp.basename(str(filename)))

        # extra load_file 之后自动保存一次,防止多个用户同时标注同一个文件夹不打钩
        self.setDirty()
        self._load_file_3d_callback()
        return True

    def loadFlags(self, flags):
        super().loadFlags(flags)
        # extra 加载json后, uniqLabelList 添加 text_flag
        for text_flag, flag in flags.items():
            if self.uniqLabelList.findItemByLabel(text_flag) is None:
                item = self.uniqLabelList.createItemFromLabel(text_flag)
                self.uniqLabelList.addItem(item)
                rgb = self._get_rgb_by_label(text_flag)
                self.uniqLabelList.setItemLabel(item, text_flag, rgb)

    # https://bbs.dlcv.ai/t/topic/357
    def dragEnterEvent(self, event):
        extensions = [
            ".%s" % fmt.data().decode().lower()
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        if event.mimeData().hasUrls():
            items = [i.toLocalFile() for i in event.mimeData().urls()]
            if any([i.lower().endswith(tuple(extensions)) for i in items]):
                event.accept()

            # extra 添加文件夹拖拽支持
            elif all([Path(i).is_dir() for i in items]):
                event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        super().dropEvent(event)
        from natsort import os_sorted

        # extra 添加文件夹拖拽支持
        items = [i.toLocalFile() for i in event.mimeData().urls()]

        file_paths = []
        suffixes = [
            ".%s" % fmt.data().decode().lower()
            for fmt in QtGui.QImageReader.supportedImageFormats()
        ]
        for item in items:
            if Path(item).is_dir():
                for suffix in suffixes:
                    str_list = [str(i) for i in Path(item).rglob(f"*{suffix}")]
                    file_paths.extend(str_list)

        self.importDroppedImageFiles(os_sorted(file_paths))

    def openDirDialog(self, _value=False, dirpath=None):
        if not self.mayContinue():
            return

        defaultOpenDirPath = dirpath if dirpath else "."
        if self.lastOpenDir and osp.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = osp.dirname(self.filename) if self.filename else "."

        targetDirPath = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                self.tr("%s - Open Directory") % __appname__,
                defaultOpenDirPath,
                QtWidgets.QFileDialog.ShowDirsOnly
                | QtWidgets.QFileDialog.DontResolveSymlinks,
            )
        )
        if targetDirPath:
            # extra 打开空文件夹，图片置空
            self.resetState()
            self.canvas.loadPixmap(QtGui.QPixmap())
        self.importDirImages(targetDirPath)

    # https://bbs.dlcv.com.cn/t/topic/421
    def deleteFile(self):
        mb = QtWidgets.QMessageBox
        msg = self.tr(
            "You are about to permanently delete this label file, " "proceed anyway?"
        )
        answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
        if answer != mb.Yes:
            return

        self.canvas.selectShapes(self.canvas.shapes)
        self.deleteSelectedShape()

    # https://bbs.dlcv.com.cn/t/topic/421
    def setDirty(self):
        super().setDirty()

        if self.imagePath is not None and Path(self.imagePath) != Path(self.filename):
            if not self.is_2_5d and not self.is_3d:
                notification(
                    dlcv_tr("Json 文件数据错误！"),
                    dlcv_tr("当前 Json 文件中的 imagePath 与图片路径不一致，请检查！"),
                    ToastPreset.ERROR,
                )
                return

        # extra 保存标签文件后,支持 ctrl+Delete 删除标签文件
        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def openPrevImg(self, _value=False):
        keep_prev = self._config["keep_prev"]
        if QtWidgets.QApplication.keyboardModifiers() == (
            Qt.ControlModifier | Qt.ShiftModifier
        ):
            self._config["keep_prev"] = True

        if not self.mayContinue():
            return

        from PyQt5 import Qt as QtControl

        event = QtControl.QKeyEvent(
            QtControl.QEvent.KeyPress, QtCore.Qt.Key.Key_Up, QtCore.Qt.NoModifier
        )

        self.fileListWidget.keyPressEvent(event)

        self._config["keep_prev"] = keep_prev

    def openNextImg(self, _value=False, load=True):
        keep_prev = self._config["keep_prev"]
        if QtWidgets.QApplication.keyboardModifiers() == (
            Qt.ControlModifier | Qt.ShiftModifier
        ):
            self._config["keep_prev"] = True

        if not self.mayContinue():
            return

        from PyQt5 import Qt as QtControl

        event = QtControl.QKeyEvent(
            QtControl.QEvent.KeyPress, QtCore.Qt.Key.Key_Down, QtCore.Qt.NoModifier
        )

        self.fileListWidget.keyPressEvent(event)

        self._config["keep_prev"] = keep_prev

    def importDirImages(self, dirpath, pattern=None, load=True):
        self.actions.openNextImg.setEnabled(True)
        self.actions.openPrevImg.setEnabled(True)

        if not self.mayContinue() or not dirpath:
            return

        self.lastOpenDir = dirpath
        self.filename = None
        self.fileListWidget.clear()

        self.fileListWidget.set_root_dir(dirpath)

        # extra 2.5d模式：导入目录时分配json文件
        if self.is_2_5d:
            # 先清空旧的映射，确保每次导入新目录时都重新分配
            self.proj_manager.clear()
            #  获取根目录路径
            root_path = dirpath
            if root_path and os.path.exists(root_path):
                self.proj_manager.assign_json_files(root_path)
        # extra End

        # https://bbs2.dlcv.com.cn/t/topic/1048/3
        dirpath = Path(dirpath)
        label_txt_path = Path(dirpath) / "label.txt"
        if label_txt_path.exists():
            self._load_label_txt(label_txt_path)
        # End
    """额外函数"""

    @property
    def imageList(self):
        from labelme.dlcv.file_tree_widget import FileTreeWidget

        if isinstance(self.fileListWidget, FileTreeWidget):
            return self.fileListWidget.image_list

    def _init_file_list_widget(self):
        from labelme.dlcv.file_tree_widget import FileTreeWidget
        from pathlib import Path

        # 替换 fileListWidget 为 FileTreeWidget
        self.fileListWidget = FileTreeWidget(self)

        def file_selection_changed():
            item = self.fileListWidget.currentItem()
            file_path = item.get_path()
            if Path(file_path).is_file():
                self.fileSelectionChanged()

        self.fileListWidget.itemSelectionChanged.connect(file_selection_changed)
        self.file_dock.setWidget(self.fileListWidget)

    def _init_ui(self):
        self._init_label_count_dock()
        self._init_setting_dock()  # 必须在所有的 docker widget 都初始化后才执行，否则 docker widget 不会 restore 成上一次退出时的状态

        def reset_all_view():
            # 重置 docker 位置
            self.file_dock.setFloating(False)
            self.setting_dock.setFloating(False)
            self.label_count_dock.setFloating(False)
            self.flag_dock.setFloating(False)
            self.shape_dock.setFloating(False)
            self.label_dock.setFloating(False)

        # 添加到菜单栏->视图->重置所有视图位置
        action_reset_view = QtWidgets.QAction(dlcv_tr("重置所有视图位置"), self)
        action_reset_view.triggered.connect(reset_all_view)
        self.menus.view.insertAction(self.menus.view.actions()[6], action_reset_view)

        self._init_3d_widget()
        self._init_file_list_widget()
        self._init_trigger_action()

        def canvas_move(pos: QtCore.QPoint):
            try:
                if self.canvas.pixmap.isNull():
                    return
                x, y = int(pos.x()), int(pos.y())
                rgb_value = self.canvas.pixmap.toImage().pixelColor(x, y).getRgb()[:-1]
                # 增加图片的宽高信息
                width = self.canvas.pixmap.width()
                height = self.canvas.pixmap.height()
                self.status(
                    f"Mouse is at: x={x}, y={y}, RGB={rgb_value}, Image Size: {width}x{height}"
                )
            except:
                notification(
                    dlcv_tr("显示RGB值失败!"), traceback.format_exc(), ToastPreset.ERROR
                )
                logger.error(traceback.format_exc())

        self.canvas.mouseMoved.disconnect()
        self.canvas.mouseMoved.connect(canvas_move)

        self._init_import_dir()

        # 文本标记
        self._init_text_flag_wgt()

        # 修改快捷键文本
        # self.actions.openNextImg.setIconText(
        #     dlcv_tr("open next image")
        #     + f"({self.actions.openNextImg.shortcut().toString()})"
        # )
        # self.actions.openPrevImg.setIconText(
        #     dlcv_tr("open previous image")
        #     + f"({self.actions.openPrevImg.shortcut().toString()})"
        # )

        # 添加 ctrl + A 全选多边形
        action = QtWidgets.QAction(dlcv_tr("全选多边形"), self)
        action.setShortcut("Ctrl+A")
        action.triggered.connect(self.select_all_shapes)
        self.addAction(action)

        # 单击标签列表，选中
        def select_shapes(item: QtWidgets.QListWidgetItem):
            shape_name = item.data(Qt.UserRole)
            self.select_shape_by_name(shape_name)

        self.uniqLabelList.itemClicked.connect(select_shapes)

        self._init_shape_color_action()

        # [新增] 连接 Canvas 的分割结束信号
        if hasattr(self.canvas, 'sig_split_finish'):
            self.canvas.sig_split_finish.connect(self.on_split_finish_callback)

    # [新增] 回调函数：处理分割后的数据同步
    def on_split_finish_callback(self, old_shape, new_shapes):
        """
        接收 Canvas 分割好的图形，进行全量状态刷新。
        参考 loadFile 的稳定性，使用 loadShapes 进行内存重载。
        """
        try:
            # 1. 先删除旧 shape 的 label（避免重复）
            self.remLabels([old_shape])
            
            # 2. 为新 shapes 添加 labels
            for new_shape in new_shapes:
                self.addLabel(new_shape)
            
            # 3. 更新 canvas 的 shapes 列表（但不替换，只更新特定部分）
            # 构造新的 Shape 列表
            current_shapes = self.canvas.shapes
            final_shapes = []
            
            # 保留没被切的，排除被切的
            for s in current_shapes:
                if s is not old_shape:
                    final_shapes.append(s)
            
            # 加入切出来的新图形
            final_shapes.extend(new_shapes)
            
            # 4. 调用 canvas.loadShapes 更新 canvas（这会重建 visible 字典等）
            self.canvas.loadShapes(final_shapes, replace=True)
            
            # 5. 选中新图形
            self.canvas.selectShapes(new_shapes)
            
            # 6. 标记文件已修改
            self.setDirty()
            
            # 7. 打印日志或通知
            logger.info(f"Split finished: 1 shape -> {len(new_shapes)} shapes")
            
        except Exception as e:
            traceback.print_exc()
            notification("分割更新失败", str(e), ToastPreset.ERROR)
    
    def select_shape_by_name(self, shape_name: str):
        select_shape = []
        for shape in self.canvas.shapes:
            if shape.label == shape_name:
                select_shape.append(shape)

        self.canvas.selectShapes(select_shape)

    def select_all_shapes(self):
        # 如果已经全选,则取消全选
        try:
            if len(self.canvas.selectedShapes) == len(self.canvas.shapes):
                self.canvas.selectShapes([])
            else:
                self.canvas.selectShapes(self.canvas.shapes)
        except:
            logger.error(traceback.format_exc())

    def _init_dlcv_ai_widget(self):
        try:
            from labelme.private.dlcv_ai_widget import DlcvAiWidget, AiController

            ai_widget = DlcvAiWidget(self)
            ai_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
            )
            # https://bbs2.dlcv.com.cn/t/topic/1690
            # 自动标注区域最大宽度：超过后控件保持左对齐，避免过长影响观感
            max_ai_toolbar_width = 520

            ai_container = QtWidgets.QWidget(self)
            ai_container.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
            )
            # 约束“工具条占用宽度”，否则 QWidgetAction 会把剩余空间全部吃掉，看起来像“长度未生效”
            ai_container.setMaximumWidth(max_ai_toolbar_width)
            ai_container_layout = QtWidgets.QHBoxLayout(ai_container)
            ai_container_layout.setContentsMargins(0, 0, 0, 0)
            ai_container_layout.setSpacing(0)
            ai_container_layout.addWidget(ai_widget)
            self.action_auto_label = QtWidgets.QAction(dlcv_tr("自动标注(L)"), self)
            self.action_auto_label.setShortcut("L")
            self.action_auto_label.triggered.connect(self.predict)
            self.addAction(self.action_auto_label)

            self.ai_widget_action = QtWidgets.QWidgetAction(self)
            self.ai_widget_action.setDefaultWidget(ai_container)
            self.actions.tool.append(self.ai_widget_action)
            self.ai_controller = AiController(ai_widget)
            self.ai_controller.sig_predict_done.connect(self.auto_label)

            def slot_ai_widget_show(enable: bool):
                self.ai_widget_action.setVisible(enable)

            self.ai_controller.sig_has_dog.connect(slot_ai_widget_show)
        except:
            pass

    # 启动后自动导入文件夹
    def _init_import_dir(self):
        # dva 文件导入
        # https://bbs.dlcv.com.cn/t/topic/398/2
        dva_file_path = None
        if len(sys.argv) > 1:
            for file_path in sys.argv[1:]:
                if file_path.lower().endswith(".dva") and Path(file_path).exists():
                    dva_file_path = file_path
                    break

        if dva_file_path:
            try:
                dva_data = yaml.safe_load(open(dva_file_path, "r", encoding="utf-8"))
            except:
                dva_data = yaml.safe_load(open(dva_file_path, "r"))

            dataset_dir = dva_data.get("dataset_dir")
            dataset_full_path = (
                Path(dva_file_path).parent / dataset_dir if dataset_dir else None
            )

            if dataset_full_path and dataset_full_path.exists():
                self.importDirImages(str(dataset_full_path))
        else:
            # https://bbs.dlcv.ai/t/topic/94
            self.lastOpenDir = self.settings.value("lastOpenDir", None)
            if len(sys.argv) > 1:  # 右键打开文件夹
                path_dir = sys.argv[1]

                # https://bbs2.dlcv.com.cn/t/topic/1532
                if len(path_dir) == 3 and path_dir[1] == ":" and path_dir[0].isalpha():
                    path_dir = f"{path_dir[0]}:"

                if Path(path_dir).is_dir() and Path(path_dir).exists():
                    self.importDirImages(path_dir)
            elif (
                self.lastOpenDir
                and Path(self.lastOpenDir).exists()
                and sys.argv[0].endswith(".py")
            ):  # 默认打开上次文件夹
                self.importDirImages(self.lastOpenDir)

    # region 标签数量统计面板
    def _init_label_count_dock(self):
        self.label_count_dock = LabelCountDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.label_count_dock)
        # 添加到菜单栏->视图->标签数量统计
        self.menus.view.insertAction(
            self.menus.view.actions()[3], self.label_count_dock.toggleViewAction()
        )

    # endregion

    # region 设置面板
    def _init_setting_dock(self):
        setting_kwargs = [
            # {
            #     'name': 'help_text',
            #     'title': tr('help text'),
            #     'type': 'text',
            #     'value': tr('help text'),
            #     'readonly': True,
            # },
            {
                "name": "proj_setting",
                "title": dlcv_tr("project setting"),
                "type": "group",
                "children": [
                    {
                        "name": "proj_type",
                        "title": dlcv_tr("project type"),
                        "type": "list",
                        "limits": [ProjEnum.NORMAL, ProjEnum.O2_5D, ProjEnum.O3D],
                        "default": ProjEnum.NORMAL,
                    },
                ],
            },
            {
                "name": "other_setting",
                "title": dlcv_tr("other setting"),
                "type": "group",
                "children": [
                    {
                        "name": "display_shape_label",
                        "title": dlcv_tr("display shape label"),
                        "type": "bool",
                        "value": True,
                        "default": True,
                        "shortcut": self._config["shortcuts"]["display_shape_label"],
                    },
                    {
                        "name": "shape_label_font_size",
                        "title": dlcv_tr("shape label font size"),
                        "type": "int",
                        "value": 8,
                        "default": 8,
                        "min": 1,
                        "max": 20,
                        "step": 1,
                    },
                    {
                        "name": "scale_option",
                        "title": dlcv_tr("keep prev scale"),
                        "type": "list",
                        "value": dlcv_tr(ScaleEnum.AUTO_SCALE),
                        "limits": [
                            dlcv_tr(ScaleEnum.KEEP_PREV_SCALE),
                            dlcv_tr(ScaleEnum.AUTO_SCALE),
                            dlcv_tr(ScaleEnum.KEEP_SCALE),
                        ],
                        "default": dlcv_tr(ScaleEnum.AUTO_SCALE),
                    },
                    {
                        "name": "convert_img_to_gray",
                        "title": dlcv_tr("convert img to gray"),
                        "type": "bool",
                        "value": STORE.convert_img_to_gray,
                        "default": STORE.convert_img_to_gray,
                    },
                    {
                        "name": "points_to_crosshair",
                        "title": dlcv_tr("points to crosshair"),
                        "type": "bool",
                        "value": STORE.canvas_points_to_crosshair,
                        "default": STORE.canvas_points_to_crosshair,
                        "tip": dlcv_tr("启用后，将点转换为十字线"),
                    },
                ],
            },
            {
                "name": "label_setting",
                "title": dlcv_tr("label setting"),
                "type": "group",
                "children": [
                    {
                        "name": "blue_line_color",
                        "title": dlcv_tr("蓝色线段标注"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                        "tip": dlcv_tr("启用后，将高亮标注线段为蓝色"),
                    },
                    {
                        "name": "slide_label",
                        "title": dlcv_tr("slide label"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                        "shortcut": self._config["shortcuts"]["canvas_auto_left_click"],
                        "tip": dlcv_tr("启用滑动标注将禁用画笔标注功能，两者互斥"),
                    },
                    {
                        "name": "slide_distance",
                        "title": dlcv_tr("slide distance"),
                        "type": "int",
                        "value": 30,
                        "default": 30,
                    },
                    {
                        "name": "brush_enabled",
                        "title": dlcv_tr("brush enabled"),
                        "type": "bool",
                        "value": STORE.canvas_brush_enabled,
                        "default": STORE.canvas_brush_enabled,
                        "shortcut": "B",
                        "tip": dlcv_tr(
                            "画笔标注功能仅适用于多边形标注模式，启用画笔标注将禁用滑动标注功能，两者互斥"
                        ),
                    },
                    {
                        "name": "fill_closed_region",
                        "title": dlcv_tr("fill closed region"),
                        "type": "bool",
                        "value": STORE.canvas_brush_fill_region,
                        "default": STORE.canvas_brush_fill_region,
                        "tip": dlcv_tr("启用后，闭合区域内部将被填充，否则仅保留轮廓"),
                    },
                    {
                        "name": "brush_size",
                        "title": dlcv_tr("brush size"),
                        "type": "int",
                        "value": STORE.canvas_brush_size,
                        "default": STORE.canvas_brush_size,
                        "min": 2,
                    },
                    {
                        "name": "highlight_start_point",
                        "title": dlcv_tr("highlight start point"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "display_rotation_arrow",
                        "title": dlcv_tr("显示旋转框箭头与角度"),
                        "type": "bool",
                        "value": STORE.canvas_display_rotation_arrow,
                        "default": STORE.canvas_display_rotation_arrow,
                    },
                    {
                        "name": "ai_polygon_simplify_epsilon",
                        "title": dlcv_tr("AI多边形点数简化设置"),
                        "type": "float",
                        "value": 0.005,
                        "default": 0.005,
                        "min": 0.001,
                        "max": 0.1,
                        "step": 0.005,
                        "tip": dlcv_tr(
                            "简化程度说明：\n0.001: 轻微简化\n0.005: 默认简化\n0.01: 较多简化\n0.05: 大量简化\n0.1: 极度简化"
                        ),
                    },
                ],
            },
            {
                "name": "auto_setting",
                "title": dlcv_tr("auto setting"),
                "type": "group",
                "children": [
                    {
                        "name": "use_bbox",
                        "title": dlcv_tr("使用Bbox进行自动标注"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "category_filter_list",
                        "title": dlcv_tr("请输入需要自动标注的类别"),
                        "type": "text",
                        "placeholder": dlcv_tr(
                            "请输入需要自动标注的类别，多个类别用,或，隔开"
                        ),
                        "value": "",
                        "tip": dlcv_tr("请输入需要自动标注的类别，多个类别用,或，隔开"),
                    },
                ],
            },
        ]

        # 快捷键提示文本
        for setting_kwarg in setting_kwargs:
            p_type = setting_kwarg.get("type")
            if p_type == "group":
                children = setting_kwarg.get("children")
                for child in children:
                    shortcut = child.get("shortcut")
                    if shortcut:
                        child["title"] = child["title"] + f"({shortcut})"

        self.parameter = Parameter.create(
            name="params", type="group", children=setting_kwargs
        )
        self.parameter_tree = ParameterTree(showHeader=False)
        self.parameter_tree.setObjectName("settingParameterTree")
        self.parameter_tree.setParameters(self.parameter, showTop=False)
        self.parameter.sigTreeStateChanged.connect(self.on_setting_dock_changed)

        # 快捷键
        for parent_kwarg in setting_kwargs:
            children = parent_kwarg.get("children")
            for child in children:
                shortcut = child.get("shortcut")
                child_type = child.get("type")
                if shortcut:
                    action = QtWidgets.QAction(self)
                    action.setShortcut(shortcut)
                    parameter = self.parameter.child(
                        parent_kwarg["name"], child["name"]
                    )
                    if child_type == "bool":
                        action.triggered.connect(
                            lambda _, p=parameter: p.setValue(not p.value())
                        )
                    elif child_type == "action":
                        action.triggered.connect(lambda _, p=parameter: p.trigger())
                    else:
                        raise ValueError(f"不支持的类型: {child_type}")
                    self.addAction(action)

        self.setting_dock = QtWidgets.QDockWidget(dlcv_tr("setting dock"), self)
        self.setting_dock.setObjectName("setting_dock")

        # https://bbs2.dlcv.com.cn/t/topic/1690
        # 将「AI Mask Model」从顶栏移到右下角设置面板
        ai_model_widget = QtWidgets.QWidget(self)
        ai_model_layout = QtWidgets.QHBoxLayout(ai_model_widget)
        ai_model_layout.setContentsMargins(6, 6, 6, 6)
        ai_model_layout.setSpacing(6)
        ai_model_label = QtWidgets.QLabel(self.tr("AI Mask Model"), ai_model_widget)
        ai_model_layout.addWidget(ai_model_label)

        # 重新创建一个 combo，避免依赖工具条上的 QWidgetAction
        self._selectAiModelComboBox = QtWidgets.QComboBox(ai_model_widget)
        self._selectAiModelComboBox.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        model_names = [model.name for model in MODELS]
        self._selectAiModelComboBox.addItems(model_names)
        if self._config["ai"]["default"] in model_names:
            model_index = model_names.index(self._config["ai"]["default"])
        else:
            logger.warning(
                "Default AI model is not found: %r",
                self._config["ai"]["default"],
            )
            model_index = 0
        self._selectAiModelComboBox.setCurrentIndex(model_index)
        self._selectAiModelComboBox.currentIndexChanged.connect(
            lambda: self.canvas.initializeAiModel(
                name=self._selectAiModelComboBox.currentText()
            )
            if self.canvas.createMode in ["ai_polygon", "ai_mask"]
            else None
        )
        ai_model_layout.addWidget(self._selectAiModelComboBox, 1)

        setting_container = QtWidgets.QWidget(self)
        setting_container.setObjectName("settingPanel")
        setting_layout = QtWidgets.QVBoxLayout(setting_container)
        # 贴近截图：整体留白 + 分组更清晰
        setting_layout.setContentsMargins(8, 8, 8, 8)
        setting_layout.setSpacing(6)
        setting_layout.addWidget(ai_model_widget)
        line = QtWidgets.QFrame(setting_container)
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        setting_layout.addWidget(line)
        setting_layout.addWidget(self.parameter_tree)

        self.setting_dock.setWidget(setting_container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.setting_dock)

        # 添加到菜单栏->视图->设置面板
        self.menus.view.insertAction(
            self.menus.view.actions()[4], self.setting_dock.toggleViewAction()
        )

        # XXX: Could be completely declarative.
        # Restore application settings.
        self.settings = QtCore.QSettings("labelme", "labelme")
        size = self.settings.value("window/size", QtCore.QSize(600, 500))
        position = self.settings.value("window/position", QtCore.QPoint(0, 0))
        state = self.settings.value("window/state", QtCore.QByteArray())
        self.resize(size)
        self.move(position)
        # or simply:
        # self.restoreGeometry(settings['window/geometry']
        self.restoreState(state)

        # 应用 UI 字体大小（如果已保存）
        try:
            ui_font_size = self.settings.value("ui/font_point_size", None, type=int)
        except Exception:
            ui_font_size = None
        if ui_font_size:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                font = app.font()
                font.setPointSize(int(ui_font_size))
                app.setFont(font)

        def restore_setting():
            setting_store = self.settings.value("setting_store", None)
            if setting_store:
                self.parameter.child("other_setting", "display_shape_label").setValue(
                    setting_store.get("display_shape_label", True)
                )
                self.parameter.child("other_setting", "convert_img_to_gray").setValue(
                    setting_store.get("convert_img_to_gray", False)
                )
                # 新增：从store中读取标签字体大小
                self.parameter.child("other_setting", "shape_label_font_size").setValue(
                    setting_store.get(
                        "shape_label_font_size", STORE.canvas_shape_label_font_size
                    )
                )
                # 新增：从store中读取点转十字设置
                self.parameter.child("other_setting", "points_to_crosshair").setValue(
                    setting_store.get("canvas_points_to_crosshair", True)
                )

                self.parameter.child("label_setting", "highlight_start_point").setValue(
                    setting_store.get("highlight_start_point", False)
                )
                # 新增：恢复旋转框箭头与角度显示
                self.parameter.child(
                    "label_setting", "display_rotation_arrow"
                ).setValue(setting_store.get("canvas_display_rotation_arrow", True))
                # 新增：恢复是否填充闭合区域设置
                self.parameter.child("label_setting", "fill_closed_region").setValue(
                    setting_store.get("canvas_brush_fill_region", True)
                )
                # 新增：恢复画笔标注设置
                self.parameter.child("label_setting", "brush_enabled").setValue(
                    setting_store.get("canvas_brush_enabled", False)
                )
                # 新增：恢复缩放选项设置
                self.parameter.child("other_setting", "scale_option").setValue(
                    setting_store.get("scale_option", dlcv_tr(ScaleEnum.AUTO_SCALE))
                )
                # 新增：恢复AI多边形简化参数设置
                self.parameter.child(
                    "label_setting", "ai_polygon_simplify_epsilon"
                ).setValue(setting_store.get("ai_polygon_simplify_epsilon", 0.005))

        restore_setting()

    def on_setting_dock_changed(
        self, root_parm: Parameter, change_parms: [[Parameter, str, bool]]
    ):
        # 使用新的参数处理方法
        self._on_param_changed(root_parm, change_parms)

    @property
    def keep_scale(self):
        return (
            self.parameter.child("other_setting", "scale_option").value()
            == dlcv_tr(ScaleEnum.KEEP_SCALE)
        )

    def _on_param_changed(self, param, changes):
        # 使用新的参数处理方法
        for param, _, new_value in changes:
            path = self.parameter.childPath(param)
            parent_path = path[:-1]
            param_name = path[-1]

            # update settings
            if len(parent_path) == 1 and parent_path[0] == "label_setting":
                if param_name == "blue_line_color":
                    # 'line_color': [0, 127, 255,255],
                    # 'vertex_fill_color': [0, 127, 255,255]
                    if new_value:
                        Shape.line_color = QtGui.QColor(0, 127, 255, 255)
                        Shape.vertex_fill_color = QtGui.QColor(0, 127, 255, 255)
                    else:
                        Shape.line_color = QtGui.QColor(0, 255, 0, 128)
                        Shape.vertex_fill_color = QtGui.QColor(0, 255, 0, 255)

                if param_name == "slide_label":
                    self.draw_polygon_with_mousemove = new_value
                    self.canvas.draw_polygon_with_mousemove = new_value
                    # 滑动标注和画笔标注互斥
                    if new_value and self.canvas.brush_enabled:
                        self.canvas.brush_enabled = False
                        STORE.set_canvas_brush_enabled(False)
                        # 更新参数面板
                        try:
                            brush_param = self.parameter.child(
                                "label_setting", "brush_enabled"
                            )
                            if brush_param:
                                brush_param.setValue(False)
                                notification(
                                    dlcv_tr("功能互斥"),
                                    dlcv_tr("已禁用画笔标注功能"),
                                    ToastPreset.INFORMATION,
                                )
                        except Exception:
                            pass
                elif param_name == "slide_distance":
                    self.canvas.two_points_distance = new_value
                elif param_name == "highlight_start_point":
                    STORE.set_canvas_highlight_start_point(new_value)
                elif param_name == "display_rotation_arrow":
                    STORE.set_canvas_display_rotation_arrow(new_value)
                elif param_name == "brush_enabled":
                    # 检查当前模式是否为多边形标注模式
                    if (
                        not self.canvas.editing()
                        and self.canvas.createMode != "polygon"
                        and new_value
                    ):
                        # 如果不是多边形标注模式，不立即启用画笔，但保留勾选状态
                        STORE.set_canvas_brush_enabled(new_value)  # 保存用户的选择
                        self.canvas.brush_enabled = False  # 但当前不启用画笔功能
                        notification(
                            dlcv_tr("画笔功能提示"),
                            dlcv_tr(
                                "画笔标注功能仅在多边形标注模式下可用，将在下次进入多边形模式时自动启用"
                            ),
                            ToastPreset.INFORMATION,
                        )
                        return

                    self.canvas.brush_enabled = new_value
                    STORE.set_canvas_brush_enabled(new_value)
                    # 画笔标注和滑动标注互斥
                    if new_value and self.canvas.draw_polygon_with_mousemove:
                        self.canvas.draw_polygon_with_mousemove = False
                        # 更新参数面板
                        try:
                            slide_param = self.parameter.child(
                                "label_setting", "slide_label"
                            )
                            if slide_param:
                                slide_param.setValue(False)
                                notification(
                                    dlcv_tr("功能互斥"),
                                    dlcv_tr("已禁用滑动标注功能"),
                                    ToastPreset.INFORMATION,
                                )
                        except Exception:
                            pass
                elif param_name == "brush_size":
                    self.canvas.brush_size = new_value
                elif param_name == "fill_closed_region":
                    STORE.set_canvas_brush_fill_region(new_value)
            elif len(parent_path) == 1 and parent_path[0] == "other_setting":
                if param_name == "display_shape_label":
                    STORE.set_canvas_display_shape_label(new_value)
                    self.canvas.update()
                # 调整标签字体大小， 更新到store中
                elif param_name == "shape_label_font_size":
                    STORE.set_canvas_shape_label_font_size(new_value)
                    self.canvas.update()
                elif param_name == "convert_img_to_gray":
                    STORE.set_convert_img_to_gray(new_value)
                # 点转十字： 当参数发生变化时，更新store中的值
                elif param_name == "points_to_crosshair":
                    STORE.set_canvas_points_to_crosshair(new_value)
                    self.canvas.update()
                elif param_name == "scale_option":
                    if new_value == dlcv_tr(ScaleEnum.KEEP_PREV_SCALE):
                        self.enableKeepPrevScale(True)
                    elif new_value == dlcv_tr(ScaleEnum.AUTO_SCALE):
                        self.enableKeepPrevScale(False)
                    elif new_value == dlcv_tr(ScaleEnum.KEEP_SCALE):
                        self.enableKeepPrevScale(False)
    # endregion

    @property
    def max_x_width(self) -> float:
        return self.image.width() - 0.001

    @property
    def max_y_height(self) -> float:
        return self.image.height() - 0.001

    # region AI
    def predict(self):
        import asyncio

        try:
            model_path = self.ai_controller.current_model_path
            img_path = self.filename
            if model_path and img_path:
                self.setEnabled(False)
                asyncio.ensure_future(self.ai_controller.predict(model_path, img_path))
        except:
            error_msg = traceback.format_exc()
            logger.error(error_msg)
            notification(
                dlcv_tr("预测失败"), dlcv_tr("请检查模型文件是否正确"), ToastPreset.ERROR
            )

    def auto_label(self, labelme_data):
        from labelme.private.dlcv_ai_widget import LabelmeData

        labelme_data: LabelmeData

        try:
            if labelme_data:
                if hasattr(labelme_data, "shapes") and labelme_data.shapes:
                    notification(
                        dlcv_tr("预测完成, 开始自动标注"),
                        dlcv_tr("请稍等..."),
                        ToastPreset.INFORMATION,
                    )
                    for shape_data in labelme_data.shapes:
                        if (
                            self.ai_controller.category_filter_list
                            and shape_data["label"]
                            not in self.ai_controller.category_filter_list
                        ):
                            continue

                        shape = Shape(**shape_data)
                        self.loadShapes([shape], replace=False)

                elif hasattr(labelme_data, "flags") and labelme_data.flags:
                    # get the first key
                    first_key = list(labelme_data.flags.keys())[0]

                    if (
                        self.ai_controller.category_filter_list
                        and first_key not in self.ai_controller.category_filter_list
                    ):
                        pass
                    else:
                        self.set_text_flag(first_key)
            notification(dlcv_tr("自动标注完成"), dlcv_tr("请检查标注结果"), ToastPreset.SUCCESS)
        except Exception as e:
            traceback_msg = traceback.format_exc()
            logger.error(traceback_msg)
            notification(dlcv_tr("自动标注失败"), str(e), ToastPreset.ERROR)

        # 保存标签
        self.canvas.shapeMoved.emit()
        self.setEnabled(True)

    def update_all_check_flag(self):
        self.action_refresh.trigger()

    # endregion

    # ----------- OCR 标注 -----------
    def set_text_flag(self, new_text_flag: str):
        # extra 只保留一个文本标记
        self.flag_widget.clear()
        item = QtWidgets.QListWidgetItem(new_text_flag)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.flag_widget.addItem(item)

        if self.uniqLabelList.findItemByLabel(new_text_flag) is None:
            item = self.uniqLabelList.createItemFromLabel(new_text_flag)
            self.uniqLabelList.addItem(item)
            rgb = self._get_rgb_by_label(new_text_flag)
            self.uniqLabelList.setItemLabel(item, new_text_flag, rgb)

        # 画布重绘以显示文本标记
        if hasattr(self, "canvas") and self.canvas:
            self.canvas.update()
        self.canvas.shapeMoved.emit()

    def get_text_flag(self) -> str:
        if self.flag_widget.count() > 0:
            item = self.flag_widget.item(0)
            return item.text()
        return ""

    # 双击编辑文本标记
    def edit_text_flag(self):
        """编辑文本标记的方法，供画布双击调用"""
        item = self.flag_widget.item(0)
        if item:
            # 读取 dialog_text_flag 的位置
            dialog_pos = self.settings.value("dialog_text_flag_pos", None)
            if dialog_pos:
                self.dialog_text_flag.move(dialog_pos)

            # 设置当前文本作为默认值
            self.dialog_text_flag.setTextValue(item.text())

            # 显示对话框并等待用户输入
            ok = self.dialog_text_flag.exec_()
            if ok:
                new_text = self.dialog_text_flag.textValue()
                if new_text.strip():  # 确保不是空文本
                    self.set_text_flag(new_text)

            # 记录 dialog_text_flag 的位置
            dialog_pos = self.dialog_text_flag.pos()
            self.settings.setValue("dialog_text_flag_pos", dialog_pos)

    def _init_text_flag_wgt(self):
        self.flag_dock.setWindowTitle(dlcv_tr("Flags"))
        self.add_text_flag_action = QtWidgets.QAction(dlcv_tr("创建文本标记"), self)
        self.add_text_flag_action.setShortcut(
            self._config["shortcuts"]["add_text_flag"]
        )
        self.addAction(self.add_text_flag_action)

        self.dialog_text_flag = QtWidgets.QInputDialog(self)
        # 对话框大一点
        self.dialog_text_flag.resize(400, 300)
        self.dialog_text_flag.setWindowTitle(dlcv_tr("Add Text Flag"))
        # 去掉标题栏的 ?
        self.dialog_text_flag.setWindowFlags(
            self.dialog_text_flag.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        )

        self.dialog_text_flag.setLabelText(dlcv_tr("Please enter the text flag"))

        def add_text_flag():
            dialog = self.dialog_text_flag
            # 读取 dialog_text_flag 的位置
            dialog_pos = self.settings.value("dialog_text_flag_pos", None)
            if dialog_pos:
                dialog.move(dialog_pos)

            old_text_flag = self.get_text_flag()

            # 如果 uniqLabelList 有选中项, 则使用选中的项作为默认值
            items = self.uniqLabelList.selectedItems()
            if items:
                old_text_flag = items[0].data(Qt.UserRole)

            if old_text_flag:
                dialog.setTextValue(old_text_flag)

            ok = dialog.exec_()
            if ok:
                text = dialog.textValue()
                self.set_text_flag(text)
                self.canvas.shapeMoved.emit()
            # 记录 dialog_text_flag 的位置
            dialog_pos = dialog.pos()
            self.settings.setValue("dialog_text_flag_pos", dialog_pos)

        self.add_text_flag_action.triggered.connect(add_text_flag)

        # 双击后 item check 状态改变
        # def change_flag_state(index: QtCore.QModelIndex):
        #     item = self.flag_widget.item(index.row())
        #     if item.checkState() == Qt.Checked:
        #         item.setCheckState(Qt.Unchecked)
        #     else:
        #         item.setCheckState(Qt.Checked)

        # self.flag_widget.itemClicked.connect(
        #     lambda _: self.actions.delete.setEnabled(True))
        # self.flag_widget.doubleClicked.connect(change_flag_state)

        # 双击编辑文本标记
        self.flag_widget.itemDoubleClicked.connect(self.edit_text_flag)

        def show_flag_menu(pos: QtCore.QPoint):
            menu = QtWidgets.QMenu()
            delete_action = QtWidgets.QAction(dlcv_tr("删除"), self)
            delete_action.setIcon(newIcon("delete"))
            menu.addAction(delete_action)

            def delete_flag():
                for item in self.flag_widget.selectedItems():
                    self.flag_widget.takeItem(self.flag_widget.row(item))

                self.canvas.shapeMoved.emit()
                # 画布重绘以更新文本标记显示
                if hasattr(self, "canvas") and self.canvas:
                    self.canvas.update()

            delete_action.triggered.connect(delete_flag)
            menu.exec_(self.flag_widget.mapToGlobal(pos))

        # self.flag_widget 是 QListWidget，右键 item 时候弹出菜单
        self.flag_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.flag_widget.customContextMenuRequested.connect(show_flag_menu)

        def uniqLabelList_item_double_clicked_callback(item: QtWidgets.QListWidgetItem):
            """双击 uniqLabelList 时, 设置 text_flag"""
            if self.get_text_flag():
                self.set_text_flag(item.data(Qt.UserRole))
                self.canvas.shapeMoved.emit()
            else:
                add_text_flag()

        # uniqLabelList 双击后设置 text_flag
        self.uniqLabelList.itemDoubleClicked.connect(
            uniqLabelList_item_double_clicked_callback
        )

        # 为 uniqLabelList 添加右键菜单删除功能
        def show_uniq_label_menu(pos: QtCore.QPoint):
            menu = QtWidgets.QMenu()
            delete_action = QtWidgets.QAction(dlcv_tr("删除标签"), self)
            delete_action.setIcon(newIcon("delete"))
            menu.addAction(delete_action)

            def delete_uniq_label():
                selected_items = self.uniqLabelList.selectedItems()
                if not selected_items:
                    return

                # 删除前询问确认
                reply = QtWidgets.QMessageBox.question(
                    self,
                    dlcv_tr("确认删除"),
                    dlcv_tr(
                        "是否确定要删除选中的 {count} 个标签？\n注意：这只会从标签列表中删除，不会影响已经标注的形状。"
                    ).format(count=len(selected_items)),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )

                if reply == QtWidgets.QMessageBox.Yes:
                    for item in selected_items:
                        row = self.uniqLabelList.row(item)
                        self.uniqLabelList.takeItem(row)

                    # 触发更新
                    self.canvas.shapeMoved.emit()

            delete_action.triggered.connect(delete_uniq_label)
            menu.exec_(self.uniqLabelList.mapToGlobal(pos))

        # 为 uniqLabelList 设置右键菜单
        self.uniqLabelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.uniqLabelList.customContextMenuRequested.connect(show_uniq_label_menu)

        # 添加创建文本标记到右键菜单
        if hasattr(self.actions, "menu"):
            # 检查是否已经添加过，避免重复添加
            if self.add_text_flag_action not in self.actions.menu:
                # 在菜单最顶部插入创建文本标记
                self.actions.menu.insert(0, self.add_text_flag_action)
                # self.actions.menu.insert(1, None)  # 分割线

                # 刷新右键菜单
                self.canvas.menus[0].clear()
                utils.addActions(self.canvas.menus[0], self.actions.menu)



    # ----------- OCR 标注 end -----------

    def fix_shape(self, shape: Shape) -> Shape:
        # 修复 shape 超出图片范围的问题
        max_x, max_y = self.max_x_width, self.max_y_height
        for point in shape.points:
            if point.x() > max_x:
                point.setX(max_x)
            elif point.x() < 0:
                point.setX(0)

            if point.y() > max_y:
                point.setY(max_y)
            elif point.y() < 0:
                point.setY(0)

        # 修复不合法多边形
        points_pos = shape.get_points_pos()
        if shape.shape_type == ShapeType.POLYGON:
            polygon = Polygon(points_pos)
            if not polygon.is_valid:
                from shapely.validation import make_valid

                repaired_polygon = make_valid(polygon)
                # 若结果为MultiPolygon，需提取面积最大的子多边形（视业务需求而定）
                if repaired_polygon.geom_type == "MultiPolygon":
                    max_polygon = max(repaired_polygon.geoms, key=lambda g: g.area)
                elif repaired_polygon.geom_type == "Polygon":
                    max_polygon = repaired_polygon
                else:
                    return shape

                shape.clear_points()
                for i, point in enumerate(max_polygon.exterior.coords):
                    shape.addPoint(QtCore.QPointF(point[0], point[1]))
        return shape

    def simplifyShapePoints(self, shape):
        """简化指定形状的轮廓点数量

        Args:
            shape: 要简化的形状对象
        """
        if not shape or len(shape.points) < 4:
            return

        try:
            import cv2
            import numpy as np
            from PyQt5 import QtCore

            # 将形状的点转换为OpenCV格式
            points = []
            for point in shape.points:
                points.append([int(point.x()), int(point.y())])

            contour = np.array(points, dtype=np.int32).reshape(-1, 1, 2)

            epsilon_factor = self.parameter.child(
                "label_setting", "ai_polygon_simplify_epsilon"
            ).value()  # 默认值

            epsilon = epsilon_factor * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # 转换回点列表格式
            simplified_points = []
            for p in approx:
                simplified_points.append(QtCore.QPointF(p[0][0], p[0][1]))

            # 如果简化后的点数仍然足够，则使用简化后的点
            if len(simplified_points) >= 3:
                # original_count = len(shape.points)
                logger.info(
                    f"简化前点数: {len(shape.points)}, 简化后点数: {len(simplified_points)}, 简化程度: {epsilon_factor}"
                )
                shape.points = simplified_points

        except ImportError:
            logger.warning("OpenCV not available, skipping shape simplification")
        except Exception as e:
            logger.error(f"Error simplifying shape points: {str(e)}")

    def is_shape_valid(self, shape: Shape) -> bool:
        points_pos = shape.get_points_pos()
        try:
            if shape.shape_type == ShapeType.POLYGON:
                polygon = Polygon(points_pos)
                return polygon.is_valid
            return True
        except:
            return False

    def is_all_shapes_valid(self) -> bool:
        # extra 检查所有多边形是否合法
        for shape in self.canvas.shapes:
            if not self.is_shape_valid(shape):
                self.canvas.selectShapes([shape])
                return False
        return True

    def toggleDrawMode(self, edit=True, createMode="polygon"):
        draw_actions = {
            "polygon": self.actions.createMode,
            "rectangle": self.actions.createRectangleMode,
            "circle": self.actions.createCircleMode,
            "point": self.actions.createPointMode,
            "line": self.actions.createLineMode,
            "linestrip": self.actions.createLineStripMode,
            "ai_polygon": self.actions.createAiPolygonMode,
            "ai_mask": self.actions.createAiMaskMode,
            "rotation": self.actions.createRotationMode,
        }

        self.canvas.setEditing(edit)
        self.canvas.createMode = createMode

        # 如果当前模式不是polygon，仅临时禁用画笔功能，但不取消勾选
        if not edit and createMode != "polygon" and self.canvas.brush_enabled:
            self.canvas.brush_enabled = False
            # 不修改STORE中的设置，这样下次进入多边形模式时可以恢复
            # 不更新参数面板的选中状态，保留用户的勾选
            notification(
                dlcv_tr("画笔功能提示"),
                dlcv_tr(
                    "画笔标注功能仅在多边形标注模式下可用，将在下次进入多边形模式时自动启用"
                ),
                ToastPreset.INFORMATION,
            )
        # 如果进入多边形模式，且STORE中画笔功能是启用的，则自动启用画笔
        elif not edit and createMode == "polygon" and STORE.canvas_brush_enabled:
            self.canvas.brush_enabled = True

        if edit:
            for draw_action in draw_actions.values():
                draw_action.setEnabled(True)
        else:
            for draw_mode, draw_action in draw_actions.items():
                draw_action.setEnabled(createMode != draw_mode)
        self.actions.editMode.setEnabled(not edit)

        if self.canvas.drawing() and self.canvas.current:
            self.canvas.current.shape_type = self.canvas.createMode

    # ------------ zx触发事件动作 ------------
    def _init_trigger_action(self):
        # 创建逆时针旋转动作
        self.z_action = QtWidgets.QAction(dlcv_tr("逆时针旋转"), self)
        self.z_action.setShortcut(STORE.get_config()["shortcuts"]["z_trigger"])
        # 添加到菜单
        self.addAction(self.z_action)

        # 创建顺时针旋转动作
        self.x_action = QtWidgets.QAction(dlcv_tr("顺时针旋转"), self)
        self.x_action.setShortcut(STORE.get_config()["shortcuts"]["x_trigger"])
        # 添加到菜单
        self.addAction(self.x_action)

        # 连接信号
        self.z_action.triggered.connect(
            lambda: self.trigger_action(angle=1.0, direction="left")
        )
        self.x_action.triggered.connect(
            lambda: self.trigger_action(angle=1.0, direction="right")
        )

    # z\x键触发
    def trigger_action(self, angle: float = 1.0, direction: str = "left"):
        # 如果在绘制模式下
        if self.canvas.drawing():
            # 如果有上一个移动点,直接标注该点
            if self.canvas.prevMovePoint:
                # 创建鼠标按下事件来模拟点击
                mouse_event = QtGui.QMouseEvent(
                    QtCore.QEvent.MouseButtonPress,
                    self.canvas.prevMovePoint,
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.NoModifier,
                )
                # 触发鼠标点击事件来标注点
                self.canvas.mousePressEvent(
                    mouse_event, need_transform=False
                )  # 修改为直接调用canvas的事件处理
        # extra End
        else:
            if not self.canvas.selectedShapes:
                return

            # 遍历所有选中的形状
            for shape in self.canvas.selectedShapes:
                # 检查是否为旋转框类型
                if shape.shape_type != "rotation":
                    continue

                if direction == "left":
                    # 执行逆时针旋转（减少角度）
                    shape.direction -= angle
                    # 保证direction在0-360度之间
                    shape.direction = shape.direction % 360

                    # 调用画布的旋转方法，传入对象和旋转角度
                    self.canvas.rotateShape(shape, -angle)
                else:
                    shape.direction += angle
                    shape.direction = shape.direction % 360
                    self.canvas.rotateShape(shape, angle)

            # 更新显示和保存
            self.canvas.shapeMoved.emit()
            self.canvas.update()

    # ------------ 属性查看方法 ------------
    def display_shape_attr(self):
        if not self.canvas.selectedShapes:
            QtWidgets.QMessageBox.information(self, dlcv_tr("提示"), dlcv_tr("请先选中一个标注"))
            return

        # 为每个选中的标注创建或更新属性窗口
        for i, shape in enumerate(self.canvas.selectedShapes):
            self.create_attribute_window(shape, i)

    # 创建属性窗口
    def create_attribute_window(self, shape, index=0):
        window_width = 240
        window_height = 120
        # 根据shape， 获取标注的中心点坐标
        center_point = shape.get_center_point()
        offset = 100
        # 1. 计算属性
        attr = get_shape_attribute(shape)
        # 2. 计算窗口显示位置
        window_x, window_y = get_window_position(
            center_point, self.canvas, window_width, window_height, offset=offset
        )

        # 3. 边界检测
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        if window_x + window_width > screen_geometry.right():
            window_x = screen_geometry.right() - window_width - 10
        if window_y + window_height > screen_geometry.bottom():
            window_y = screen_geometry.bottom() - window_height - 10

        # 创建并显示窗口
        attr_widget = viewAttribute(
            attr["width"], attr["height"], attr["area"], parent=self
        )
        attr_widget.setGeometry(window_x, window_y, window_width, window_height)
        attr_widget.setWindowTitle(
            f"{dlcv_tr('属性')} - {shape.label if shape.label else dlcv_tr('标注') + str(index + 1)}"
        )
        attr_widget.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowCloseButtonHint  # 关闭按钮
            | QtCore.Qt.WindowStaysOnTopHint  # 保持窗口在其他窗口之上
        )
        attr_widget.show()
        attr_widget.raise_()

    # ------------ 属性查看方法 end ------------

    # ------------ 编辑和绘制状态切换新动作 ------------
    def _init_edit_mode_action(self):
        # 创建一个新动作用于编辑和绘制状态切换
        self.edit_mode_action = QtWidgets.QAction(dlcv_tr("编辑和绘制状态切换"), self)
        self.edit_mode_action.setShortcut(STORE.get_config()["shortcuts"]["edit_mode"])
        self.addAction(self.edit_mode_action)
        self.edit_mode_action.triggered.connect(self.toggle_edit_mode)

    # 添加一个新的动作用于编辑和绘制状态切换
    def toggle_edit_mode(self):

        # 如果当前在绘制状态,切换到编辑状态
        if not self.canvas.editing():
            # 如果正在绘制, 清除当前标注
            if self.canvas.current is not None:
                self.canvas.current = None
                self.canvas.line.points = []
                self.canvas.line.point_labels = []
                # 刷新
                self.canvas.update()
            # 记录当前的绘制模式
            self._prev_create_mode = self.canvas.createMode
            self.toggleDrawMode(True)
        # 如果在编辑状态,切换回之前的绘制模式
        else:
            # 存在记录的绘制模式,切换回之前的绘制模式
            if hasattr(self, "_prev_create_mode"):
                self.toggleDrawMode(False, createMode=self._prev_create_mode)
            else:
                # 不存在记录的绘制模式,切换到多边形模式
                self._prev_create_mode = 'polygon'
                self.toggleDrawMode(False, createMode=self._prev_create_mode)
            

    # ------------ 编辑和绘制状态切换新动作 end ------------

    # ------------ 3D 视图 ------------
    def _init_3d_widget(self):
        from labelme.dlcv.widget_25d_3d.o3dwidget import O3DWidget
        from labelme.dlcv.widget_25d_3d.manager import ProjManager

        self.o3d_widget = O3DWidget()
        self.proj_manager = ProjManager()

        old_center_widget = self.centralWidget()
        # 创建QSplitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.o3d_widget)
        splitter.addWidget(old_center_widget)
        self.setCentralWidget(splitter)

        # 不允许子控件被折叠到0
        splitter.setChildrenCollapsible(False)

        if self.is_3d:
            self.o3d_widget.show()
        else:
            self.o3d_widget.hide()

        self.parameter.child("proj_setting", "proj_type").sigValueChanged.connect(
            self.proj_type_changed
        )
        self.parameter.child("proj_setting", "proj_type").setValue(
            self.settings.value("proj_type", ProjEnum.NORMAL)
        )

        self.__restore_splitter_sizes()

    @property
    def is_3d(self) -> bool:
        return self.parameter.child("proj_setting", "proj_type").value() == ProjEnum.O3D

    @property
    def is_2_5d(self) -> bool:
        return self.parameter.child("proj_setting", "proj_type").value() == ProjEnum.O2_5D

    # 项目类型切换
    def proj_type_changed(self, param: Parameter, new_value: str):
        if self.is_3d:
            self.o3d_widget.show()
        else:
            self.o3d_widget.hide()

        # 2.5D模式切换处理
        was_2_5d = bool(self.proj_manager._file_to_json)  # 检查之前是否是2.5D模式
        if new_value == ProjEnum.O2_5D:
            print('切入2.5D模式')
            if self.lastOpenDir:
                self.proj_manager.assign_json_files(self.lastOpenDir)
                self.fileListWidget.update_state()
        else:
            print('切出2.5D模式')
            # 切换到非2.5D模式时，清空2.5D映射
            self.proj_manager.clear()
            # 如果之前是2.5D模式，切出时需要更新状态
            if was_2_5d and self.lastOpenDir:
                self.fileListWidget.update_state()

        self.settings.setValue("proj_type", new_value)


    def _load_file_3d_callback(self):
        if not self.is_3d:
            return

        img_path = self.filename
        if not self.proj_manager.is_3d_data(img_path):
            notification(
                dlcv_tr("3D 视图提示"),
                dlcv_tr("当前图片不是3D数据，无法显示3D视图"),
                ToastPreset.WARNING,
            )
            return

        gray_img_path = self.proj_manager.get_gray_img_path(img_path)
        depth_img_path = self.proj_manager.get_depth_img_path(img_path)
        self.o3d_widget.display_with_path(gray_img_path, depth_img_path)

    def __store_splitter_sizes(self):
        sizes = self.centralWidget().sizes()
        self.settings.setValue(
            "o3d_widget_splitter_sizes",
            sizes,
        )

    def __restore_splitter_sizes(self):
        sizes = self.settings.value("o3d_widget_splitter_sizes")
        if sizes:
            sizes = int(sizes[0]), int(sizes[1])
            self.centralWidget().setSizes(sizes)


def init_backend_ws():
    """初始化全局 backend_ws 对象"""
    import websocket
    import threading
    from labelme.utils import logger
    from labelme.dlcv.store import STORE
    port = 13888
    STORE.backend_ws = None
    def ws_thread():
        """在后台线程中保持 websocket 连接"""
        try:
            ws = websocket.WebSocketApp(
                f"ws://localhost:{port}/ws/lock"
            )
            STORE.backend_ws = ws
            ws.run_forever()
        except Exception as e:
            STORE.backend_ws = None
            logger.error(f"WebSocket connection failed: {e}")
    
    # 在后台线程中启动 websocket 连接
    thread = threading.Thread(target=ws_thread, daemon=True)
    thread.start()

class ProjEnum:
    NORMAL = "2D"
    O2_5D = "2.5D"
    O3D = "3D"
    # ------------ 3D 视图 end ------------


class ScaleEnum:
    KEEP_PREV_SCALE = "保持上次缩放比例"
    AUTO_SCALE = "自动缩放"
    KEEP_SCALE = "保持缩放比例"
