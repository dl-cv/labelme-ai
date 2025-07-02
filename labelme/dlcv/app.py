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
from PIL import ImageFile
import yaml

from labelme import __appname__
from labelme.app import *
from labelme.dlcv.utils_func import notification, normalize_16b_gray_to_uint8
from labelme.dlcv.store import STORE
from labelme.dlcv import tr
from labelme.utils.qt import removeAction, newIcon
from shapely.geometry import Polygon
from labelme.dlcv.shape import ShapeType
from labelme.utils import print_time  # noqa
from labelme.dlcv.shape import Shape
from typing import List
from labelme.dlcv.widget.viewAttribute import get_shape_attribute, get_window_position, viewAttribute
from labelme.dlcv.widget.clipboard import copy_file_to_clipboard
ImageFile.LOAD_TRUNCATED_IMAGES = True  # 解决图片加载失败问题


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


class MainWindow(MainWindow):
    canvas: labelme.dlcv.canvas.Canvas
    sig_auto_label_all_update = QtCore.Signal(object)

    def __init__(
            self, config=None, filename=None, output=None, output_file=None, output_dir=None
    ):
        # extra 额外属性
        self.action_refresh = None
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

        self.menus.help.actions()[0].setText("使用文档")

        self._init_dev_mode()
        self._init_ui()
        self._init_copy_image()  # 必须在初始化时调用

        # 使用 store 存储数据
        STORE.set_edit_label_name(self._edit_label)

    # https://bbs.dlcv.com.cn/t/topic/590
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
        action = QtWidgets.QAction("开发者模式", self)
        action.setShortcut("Ctrl+L")
        action.setCheckable(True)
        action.triggered.connect(self.dev_dialog_popup)
        self.addAction(action)

    def dev_dialog_popup(self):
        dialog = QtWidgets.QDialog(self, Qt.WindowCloseButtonHint)
        dialog.setWindowTitle("开发者模式")
        dialog.setFixedSize(400, 300)

        layout = QtWidgets.QVBoxLayout()
        dialog.setLayout(layout)

        label = QtWidgets.QLabel("开发者密码")
        line_edit = QtWidgets.QLineEdit()
        line_edit.setEchoMode(QtWidgets.QLineEdit.Password)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(label)
        top_layout.addWidget(line_edit)
        layout.addLayout(top_layout)

        button = QtWidgets.QPushButton("确定")
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
        url = 'https://github.com/labelmeai/labelme/tree/main/examples/tutorial'
        # url = "https://bbs.dlcv.com.cn/labelmeai"  # NOQA
        webbrowser.open(url)

    # https://bbs.dlcv.ai/t/topic/89
    # https://bbs.dlcv.ai/t/topic/90
    def populateModeActions(self):
        # 移除 [打开文件] 功能
        self.actions.tool = list(self.actions.tool[1:])

        # 创建AI多边形,添加快捷键文本
        ai_polygon_mode = self.actions.createAiPolygonMode
        ai_polygon_mode.setIconText(
            ai_polygon_mode.text() + f"({ai_polygon_mode.shortcut().toString()})"
        )
        self.actions.tool.insert(7, self.actions.createAiPolygonMode)

        # https://bbs.dlcv.com.cn/t/topic/1050
        # 刷新功能
        def refresh():
            self.fileListWidget.update_state()

        self.action_refresh = utils.newAction(
            self,
            "刷新(F5)",
            refresh,
            "F5",
            "refresh",
            "刷新文件夹",
        )
        self.addAction(self.action_refresh)
        self.actions.tool.insert(14, self.action_refresh)

        # 创建旋转框模式
        create_action = functools.partial(utils.newAction, self)
        createRotationMode = create_action(
            self.tr("创建旋转框"),
            lambda: self.toggleDrawMode(False, createMode="rotation"),
            "R",  # 快捷键
            "objects",
            self.tr("开始绘制旋转框 (R)"),
            enabled=False,
        )
        self.actions.createRotationMode = createRotationMode
        self.actions.tool.insert(7, self.actions.createRotationMode)  # 插入到合适位置

        # 亮度对比度禁用
        # https://bbs.dlcv.ai/t/topic/328
        self.actions.brightnessContrast.setVisible(False)

        # 编辑多边形,添加快捷键文本
        tool_action = self.actions.tool[8]
        tool_action.setIconText(
            self.actions.tool[8].text() + f"({tool_action.shortcut().toString()})"
        )

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
            self.actions.createCircleMode,
            self.actions.createLineMode,
            self.actions.createPointMode,
            self.actions.createLineStripMode,
            self.actions.createRotationMode,  # 添加旋转框模式
            self.actions.createAiPolygonMode,
            self.actions.editMode,
        )
        utils.addActions(self.menus.edit, actions + self.actions.editMenu)

        # 添加查看属性动作
        self.actions.action_view_shape_attr = QtWidgets.QAction("查看属性", self)
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

    # https://bbs.dlcv.ai/t/topic/94
    def closeEvent(self, event):
        super().closeEvent(event)
        self.settings.setValue("lastOpenDir", self.lastOpenDir)

        # extra 保存设置
        setting_store = {
            "display_shape_label": STORE.canvas_display_shape_label,
            "highlight_start_point": STORE.canvas_highlight_start_point,
            "convert_img_to_gray": STORE.convert_img_to_gray,
            "canvas_display_rotation_arrow": STORE.canvas_display_rotation_arrow,
            "canvas_brush_fill_region": STORE.canvas_brush_fill_region,
            "canvas_brush_enabled": STORE.canvas_brush_enabled,  # 新增：保存画笔标注设置
            "canvas_brush_size": STORE.canvas_brush_size,  # 新增：保存画笔大小
            "scale_option": self.parameter.child("other_setting", "scale_option").value()
        }
        self.settings.setValue("setting_store", setting_store)
        self.__store_splitter_sizes()
        # extra End
    
    # 复制文件到剪贴板
    def copy_image(self):
        # 获取当前画布显示的图片路径
        file_path = getattr(self, "imagePath", None)

        if file_path:
            try:
                copy_file_to_clipboard(file_path)
                notification(
                    "复制成功",
                    "图片已复制到剪贴板，可直接粘贴为文件。",
                    ToastPreset.SUCCESS,
                )
            except Exception as e:
                notification(
                    "复制失败",
                    str(e),
                    ToastPreset.ERROR,
                )
        else:
            notification(
                "提示",
                "请先选中一张图片。",
                ToastPreset.WARNING,
            )

    # 新增复制文件动作，并添加快捷键
    def _init_copy_image(self):
        # 复制图片快捷键
        action_copy = QtWidgets.QAction("复制文件", self)
        action_copy.setShortcut("Ctrl+C")
        action_copy.triggered.connect(self.copy_image)
        self.addAction(action_copy)


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
    # 保存 json 的函数
    def saveLabels(self, filename: str):
        """ filename: json 文件路径 """
        # extra 保存 3d json
        if self.is_3d:
            filename = self.getLabelFile()
        # extra End

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
            flag = item.checkState() == Qt.Checked
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
            return True

        # 不需要保存 False 的 flag
        flags = {k: v for k, v in flags.items() if v}
        # extra End

        try:
            imagePath = osp.relpath(self.imagePath, osp.dirname(filename))
            imageData = self.imageData if self._config["store_data"] else None
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))

            # extra 3D 需要保存3D数据
            if self.is_3d and self.otherData is not None:
                self.otherData.update({
                    'img_name_list': self.proj_manager.get_img_name_list(self.filename),
                })

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
            items = self.fileListWidget.findItems(self.imagePath, Qt.MatchExactly)
            if len(items) > 0:
                # if len(items) != 1:
                #     raise RuntimeError("There are duplicate files.")
                for item in items:
                    item.setCheckState(Qt.Checked)
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
                # 彻底清理取消标签输入后的状态
                self._cancel_shape_creation()
                return

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
            if shape.shape_type == ShapeType.ROTATION and not hasattr(shape, "direction"):
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

    def pasteSelectedShape(self):
        if not self._copied_shapes:
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

    def getLabelFile(self) -> str:
        try:
            assert self.filename is not None
            return self.proj_manager.get_json_path(self.filename)
        except:
            notification(title="获取标签文件失败", text="代码不应该运行到这里", preset=ToastPreset.ERROR)
            raise Exception("获取标签文件失败")

    def get_vertical_scrollbar(self):
        return self.scrollBars[Qt.Vertical]

    def get_horizontal_scrollbar(self):
        return self.scrollBars[Qt.Horizontal]

    def loadFile(self, filename=None):
        """Load the specified file, or the last opened file if None."""
        # changing fileListWidget loads file
        if filename in self.imageList and (
                self.fileListWidget.currentRow() != self.imageList.index(filename)
        ):
            self.fileListWidget.setCurrentRow(self.imageList.index(filename))
            self.fileListWidget.repaint()
            return

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
        if isinstance(filename, str):
            file_path = filename.encode("utf-8")
        cv_img = cv2.imdecode(
            np.fromfile(file_path, dtype=np.uint8),
            cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH,
        )
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
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))

        if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
            try:
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

        # extra 保存标签文件后,支持 ctrl+Delete 删除标签文件
        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def importDirImages(self, dirpath, pattern=None, load=True):
        self.actions.openNextImg.setEnabled(True)
        self.actions.openPrevImg.setEnabled(True)

        if not self.mayContinue() or not dirpath:
            return

        self.lastOpenDir = dirpath
        self.filename = None
        self.fileListWidget.clear()

        self.fileListWidget.set_root_dir(dirpath)

        self.openNextImg(load=load)

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

        self.fileListWidget.itemSelectionChanged.connect(
            file_selection_changed
        )
        self.file_dock.setWidget(self.fileListWidget)

    def _init_ui(self):
        self._init_setting_dock()
        self._init_3d_widget()
        self._init_file_list_widget()
        self._init_rotate_shape_action()


        def canvas_move(pos: QtCore.QPoint):
            try:
                if self.canvas.pixmap.isNull():
                    return
                x, y = int(pos.x()), int(pos.y())
                rgb_value = self.canvas.pixmap.toImage().pixelColor(x, y).getRgb()[:-1]
                # 获取图片的宽高
                width = self.canvas.pixmap.width()
                height = self.canvas.pixmap.height()
                self.status(f"Mouse is at: x={x}, y={y}, RGB={rgb_value}, Image Size: {width}x{height}")
            except:
                notification(
                    "显示rgb值失败!", traceback.format_exc(), ToastPreset.ERROR
                )
                logger.error(traceback.format_exc())
        self.canvas.mouseMoved.disconnect()
        self.canvas.mouseMoved.connect(canvas_move)

        self._init_import_dir()

        # 文本标记
        self._init_text_flag_wgt()

        # 修改快捷键文本
        self.actions.openNextImg.setIconText(
            tr("open next image")
            + f"({self.actions.openNextImg.shortcut().toString()})"
        )
        self.actions.openPrevImg.setIconText(
            tr("open previous image")
            + f"({self.actions.openPrevImg.shortcut().toString()})"
        )

        # 添加 ctrl + A 全选多边形
        action = QtWidgets.QAction("全选多边形", self)
        action.setShortcut("Ctrl+A")
        action.triggered.connect(self.select_all_shapes)
        self.addAction(action)

        # 单击标签列表，选中
        def select_shapes(item: QtWidgets.QListWidgetItem):
            shape_name = item.data(Qt.UserRole)
            self.select_shape_by_name(shape_name)

        self.uniqLabelList.itemClicked.connect(select_shapes)

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
            self.action_auto_label = QtWidgets.QAction("自动标注(L)", self)
            self.action_auto_label.setShortcut("L")
            self.action_auto_label.triggered.connect(self.predict)
            self.addAction(self.action_auto_label)

            self.ai_widget_action = QtWidgets.QWidgetAction(self)
            self.ai_widget_action.setDefaultWidget(ai_widget)
            self.actions.tool.append(self.ai_widget_action)
            self.ai_controller = AiController(ai_widget)
            self.ai_controller.sig_predict_done.connect(self.auto_label)

            def enable_dlcv_ai_widget(enable: bool):
                if enable:
                    self.ai_widget_action.setVisible(True)
                else:
                    self.ai_widget_action.setVisible(False)

            self.ai_controller.sig_enable.connect(enable_dlcv_ai_widget)
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
                if Path(path_dir).is_dir() and Path(path_dir).exists():
                    self.importDirImages(path_dir)
            elif (
                    self.lastOpenDir
                    and Path(self.lastOpenDir).exists()
                    and sys.argv[0].endswith(".py")
            ):  # 默认打开上次文件夹
                self.importDirImages(self.lastOpenDir)

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
                "title": tr("project setting"),
                "type": "group",
                "children": [
                    {
                        "name": "proj_type",
                        "title": tr("project type"),
                        "type": "list",
                        "limits": [ProjEnum.NORMAL, ProjEnum.O3D],
                        "default": ProjEnum.NORMAL,
                    },
                ],
            },
            {
                "name": "other_setting",
                "title": tr("other setting"),
                "type": "group",
                "children": [
                    {
                        "name": "display_shape_label",
                        "title": tr("display shape label"),
                        "type": "bool",
                        "value": True,
                        "default": True,
                        "shortcut": self._config["shortcuts"]["display_shape_label"],
                    },
                    {
                        "name": "scale_option",
                        "title": tr("keep prev scale"),
                        "type": "list",
                        "value": ScaleEnum.AUTO_SCALE,
                        "limits": [ScaleEnum.KEEP_PREV_SCALE, ScaleEnum.AUTO_SCALE, ScaleEnum.KEEP_SCALE],
                        "default": ScaleEnum.AUTO_SCALE,
                    },
                    {
                        "name": "convert_img_to_gray",
                        "title": tr("convert img to gray"),
                        "type": "bool",
                        "value": STORE.convert_img_to_gray,
                        "default": STORE.convert_img_to_gray,
                    },
                ],
            },
            {
                "name": "label_setting",
                "title": tr("label setting"),
                "type": "group",
                "children": [
                    {
                        "name": "slide_label",
                        "title": tr("slide label"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                        "shortcut": self._config["shortcuts"]["canvas_auto_left_click"],
                        "tip": "启用滑动标注将禁用画笔标注功能，两者互斥",
                    },
                    {
                        "name": "slide_distance",
                        "title": tr("slide distance"),
                        "type": "int",
                        "value": 30,
                        "default": 30,
                    },
                    {
                        "name": "brush_enabled",
                        "title": tr("brush enabled"),
                        "type": "bool",
                        "value": STORE.canvas_brush_enabled,
                        "default": STORE.canvas_brush_enabled,
                        "shortcut": "B",
                        "tip": "画笔标注功能仅适用于多边形标注模式，启用画笔标注将禁用滑动标注功能，两者互斥",
                    },
                    {
                        "name": "fill_closed_region",
                        "title": tr("fill closed region"),
                        "type": "bool",
                        "value": STORE.canvas_brush_fill_region,
                        "default": STORE.canvas_brush_fill_region,
                        "tip": "启用后，闭合区域内部将被填充，否则仅保留轮廓",
                    },
                    {
                        "name": "brush_size",
                        "title": tr("brush size"),
                        "type": "int",
                        "value": STORE.canvas_brush_size,
                        "default": STORE.canvas_brush_size,
                        "min": 3,
                    },
                    {
                        "name": "highlight_start_point",
                        "title": tr("highlight start point"),
                        "type": "bool",
                        "value": False,
                        "default": False,
                    },
                    {
                        "name": "display_rotation_arrow",
                        "title": tr("显示旋转框箭头与角度"),
                        "type": "bool",
                        "value": STORE.canvas_display_rotation_arrow,
                        "default": STORE.canvas_display_rotation_arrow,
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

        self.setting_dock = QtWidgets.QDockWidget(tr("setting dock"), self)
        self.setting_dock.setObjectName("setting_dock")
        self.setting_dock.setWidget(self.parameter_tree)
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

        def restore_setting():
            setting_store = self.settings.value("setting_store", None)
            if setting_store:
                self.parameter.child("other_setting", "display_shape_label").setValue(
                    setting_store.get("display_shape_label", True)
                )
                self.parameter.child("other_setting", "convert_img_to_gray").setValue(
                    setting_store.get("convert_img_to_gray", False)
                )

                self.parameter.child("label_setting", "highlight_start_point").setValue(
                    setting_store.get("highlight_start_point", False)
                )
                # 新增：恢复旋转框箭头与角度显示
                self.parameter.child("label_setting", "display_rotation_arrow").setValue(
                    setting_store.get("canvas_display_rotation_arrow", True)
                )
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
                    setting_store.get("scale_option", ScaleEnum.AUTO_SCALE)
                )
                # 更新STORE中的值
                STORE.set_canvas_brush_fill_region(
                    setting_store.get("canvas_brush_fill_region", True)
                )
                STORE.set_canvas_brush_enabled(
                    setting_store.get("canvas_brush_enabled", False)
                )
                STORE.set_canvas_brush_size(
                    setting_store.get("canvas_brush_size", 3)
                )

        restore_setting()

    def on_setting_dock_changed(
            self, root_parm: Parameter, change_parms: [[Parameter, str, bool]]
    ):
        # 使用新的参数处理方法
        self._on_param_changed(root_parm, change_parms)

    @property
    def keep_scale(self):
        return self.parameter.child("other_setting", "scale_option").value() == ScaleEnum.KEEP_SCALE

    def _on_param_changed(self, param, changes):
        # 使用新的参数处理方法
        for param, _, new_value in changes:
            path = self.parameter.childPath(param)
            parent_path = path[:-1]
            param_name = path[-1]

            # update settings
            if len(parent_path) == 1 and parent_path[0] == "label_setting":
                if param_name == "slide_label":
                    self.draw_polygon_with_mousemove = new_value
                    self.canvas.draw_polygon_with_mousemove = new_value
                    # 滑动标注和画笔标注互斥
                    if new_value and self.canvas.brush_enabled:
                        self.canvas.brush_enabled = False
                        STORE.set_canvas_brush_enabled(False)
                        # 更新参数面板
                        try:
                            brush_param = self.parameter.child("label_setting", "brush_enabled")
                            if brush_param:
                                brush_param.setValue(False)
                                notification("功能互斥", "已禁用画笔标注功能", ToastPreset.INFORMATION)
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
                    if not self.canvas.editing() and self.canvas.createMode != "polygon" and new_value:
                        # 如果不是多边形标注模式，不立即启用画笔，但保留勾选状态
                        STORE.set_canvas_brush_enabled(new_value)  # 保存用户的选择
                        self.canvas.brush_enabled = False  # 但当前不启用画笔功能
                        notification("画笔功能提示",
                                     "画笔标注功能仅在多边形标注模式下可用，将在下次进入多边形模式时自动启用",
                                     ToastPreset.INFORMATION)
                        return

                    self.canvas.brush_enabled = new_value
                    STORE.set_canvas_brush_enabled(new_value)
                    # 画笔标注和滑动标注互斥
                    if new_value and self.canvas.draw_polygon_with_mousemove:
                        self.canvas.draw_polygon_with_mousemove = False
                        # 更新参数面板
                        try:
                            slide_param = self.parameter.child("label_setting", "slide_label")
                            if slide_param:
                                slide_param.setValue(False)
                                notification("功能互斥", "已禁用滑动标注功能", ToastPreset.INFORMATION)
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
                elif param_name == "convert_img_to_gray":
                    STORE.set_convert_img_to_gray(new_value)
                elif param_name == "scale_option":
                    if new_value == ScaleEnum.KEEP_PREV_SCALE:
                        self.enableKeepPrevScale(True)
                    elif new_value == ScaleEnum.AUTO_SCALE:
                        self.enableKeepPrevScale(False)
                    elif new_value == ScaleEnum.KEEP_SCALE:
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
            notification("预测失败", "请检查模型文件是否正确", ToastPreset.ERROR)

    def auto_label(self, shape_list: List[dict[str, any]]):
        # response_data: BaseResponse
        # {'sample_results': [{'results': [{'area': 520, 'bbox': [309.0119323730469, 35.99763488769531,
        # 338.2671813964844, 73.18121337890625], 'category_id': 0, 'category_name': '气球',
        # 'mask': 'i/yDEkyJJMmQJEOSDEky60EoA9/A',
        # 'score': 0.05747972056269646, 'with_mask': True}]}], 'code': '00000', 'task_type': '检测'}
        # print(response_data)
        try:
            if shape_list:
                notification("预测完成, 开始自动标注", "请稍等...", ToastPreset.INFORMATION)

                for shape_data in shape_list:
                    shape = Shape(**shape_data)
                    self.loadShapes([shape], replace=False)

                notification("自动标注完成", "请检查标注结果", ToastPreset.SUCCESS)
        except Exception as e:
            traceback_msg = traceback.format_exc()
            logger.error(traceback_msg)
            notification("自动标注失败", str(e), ToastPreset.ERROR)

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

    def get_text_flag(self) -> str:
        if self.flag_widget.count() > 0:
            item = self.flag_widget.item(0)
            return item.text()
        return ""

    def _init_text_flag_wgt(self):
        self.flag_dock.setWindowTitle(tr("Flags"))
        self.add_text_flag_action = QtWidgets.QAction("添加文本标记", self)
        self.add_text_flag_action.setShortcut(
            self._config["shortcuts"]["add_text_flag"]
        )
        self.addAction(self.add_text_flag_action)

        self.dialog_text_flag = QtWidgets.QInputDialog(self)
        # 对话框大一点
        self.dialog_text_flag.resize(400, 300)
        self.dialog_text_flag.setWindowTitle(tr("Add Text Flag"))
        self.dialog_text_flag.setLabelText(tr("Please enter the text flag"))

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
        def change_flag_state(index: QtCore.QModelIndex):
            item = self.flag_widget.item(index.row())
            if item.checkState() == Qt.Checked:
                item.setCheckState(Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)

        self.flag_widget.itemClicked.connect(
            lambda _: self.actions.delete.setEnabled(True)
        )
        self.flag_widget.doubleClicked.connect(change_flag_state)

        def show_flag_menu(pos: QtCore.QPoint):
            menu = QtWidgets.QMenu()
            delete_action = QtWidgets.QAction("删除", self)
            delete_action.setIcon(newIcon("delete"))
            menu.addAction(delete_action)

            def delete_flag():
                for item in self.flag_widget.selectedItems():
                    self.flag_widget.takeItem(self.flag_widget.row(item))

                self.canvas.shapeMoved.emit()

            delete_action.triggered.connect(delete_flag)
            menu.exec_(self.flag_widget.mapToGlobal(pos))

        # self.flag_widget 是 QListWidget，右键 item 时候弹出菜单
        self.flag_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.flag_widget.customContextMenuRequested.connect(show_flag_menu)

        def uniqLabelList_item_double_clicked_callback(item: QtWidgets.QListWidgetItem):
            """ 双击 uniqLabelList 时, 设置 text_flag """
            if self.get_text_flag():
                self.set_text_flag(item.data(Qt.UserRole))
                self.canvas.shapeMoved.emit()
            else:
                add_text_flag()

        # uniqLabelList 双击后设置 text_flag
        self.uniqLabelList.itemDoubleClicked.connect(uniqLabelList_item_double_clicked_callback)

        # 为 uniqLabelList 添加右键菜单删除功能
        def show_uniq_label_menu(pos: QtCore.QPoint):
            menu = QtWidgets.QMenu()
            delete_action = QtWidgets.QAction("删除标签", self)
            delete_action.setIcon(newIcon("delete"))
            menu.addAction(delete_action)

            def delete_uniq_label():
                selected_items = self.uniqLabelList.selectedItems()
                if not selected_items:
                    return

                # 删除前询问确认
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "确认删除",
                    f"是否确定要删除选中的 {len(selected_items)} 个标签？\n注意：这只会从标签列表中删除，不会影响已经标注的形状。",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No
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
            "rotation": self.actions.createRotationMode,  # 添加旋转框支持
        }

        self.canvas.setEditing(edit)
        self.canvas.createMode = createMode

        # 如果当前模式不是polygon，仅临时禁用画笔功能，但不取消勾选
        if not edit and createMode != "polygon" and self.canvas.brush_enabled:
            self.canvas.brush_enabled = False
            # 不修改STORE中的设置，这样下次进入多边形模式时可以恢复
            # 不更新参数面板的选中状态，保留用户的勾选
            notification("画笔功能提示", "画笔标注功能仅在多边形标注模式下可用，将在下次进入多边形模式时自动启用",
                         ToastPreset.INFORMATION)
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

    # ------------ 旋转框 ------------
    def _init_rotate_shape_action(self):
        # 创建逆时针旋转动作
        self.rotate_left_action = QtWidgets.QAction("逆时针旋转", self)
        self.rotate_left_action.setShortcut(
            STORE.get_config()['shortcuts']['rotate_left']
        )
        # 添加到菜单
        self.addAction(self.rotate_left_action)

        # 创建顺时针旋转动作
        self.rotate_right_action = QtWidgets.QAction("顺时针旋转", self)
        self.rotate_right_action.setShortcut(
            STORE.get_config()['shortcuts']['rotate_right']
        )
        # 添加到菜单
        self.addAction(self.rotate_right_action)

        # 连接信号
        self.rotate_left_action.triggered.connect(lambda: self.rotate_shape(angle=1.0, direction="left"))
        self.rotate_right_action.triggered.connect(lambda: self.rotate_shape(angle=1.0, direction="right"))

    # 旋转框旋转
    def rotate_shape(self, angle: float = 1.0, direction: str = "left"):
        """旋转选中的旋转框,支持多选"""

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

    # ------------ 旋转框 end ------------


    # ------------ 属性查看方法 ------------
    def display_shape_attr(self):
        if not self.canvas.selectedShapes:
            QtWidgets.QMessageBox.information(self, "提示", "请先选中一个标注")
            return

        # 为每个选中的标注创建或更新属性窗口
        for i, shape in enumerate(self.canvas.selectedShapes):
            self.create_attribute_window(shape, i)

    # 创建属性窗口
    def create_attribute_window(self, shape, index=0):
        window_width = 240
        window_height = 120

        # 1. 计算属性
        attr = get_shape_attribute(shape)
        # 2. 计算窗口显示位置
        window_x, window_y = get_window_position(shape, self.canvas, window_width, window_height, offset=0)

        window_x += 200
        window_y += 200

        # 3. 边界检测
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        if window_x + window_width > screen_geometry.right():
            window_x = screen_geometry.right() - window_width - 10
        if window_y + window_height > screen_geometry.bottom():
            window_y = screen_geometry.bottom() - window_height - 10

        # 创建并显示窗口
        attr_widget = viewAttribute(attr['width'], attr['height'], attr['area'], parent=self)
        attr_widget.setGeometry(window_x, window_y, window_width, window_height)
        attr_widget.setWindowTitle(f"属性 - {shape.label if shape.label else f'标注{index+1}'}")
        attr_widget.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowCloseButtonHint | # 关闭按钮
            QtCore.Qt.WindowStaysOnTopHint # 保持窗口在其他窗口之上
        )
        attr_widget.show()
        attr_widget.raise_()

    # ------------ 属性查看方法 end ------------

    # ------------ 3D 视图 ------------
    def _init_3d_widget(self):
        from labelme.dlcv.widget_3d.o3dwidget import O3DWidget
        from labelme.dlcv.widget_3d.manager import ProjManager

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

        self.parameter.child("proj_setting", "proj_type").sigValueChanged.connect(self.proj_type_changed)
        self.parameter.child("proj_setting", "proj_type").setValue(
            self.settings.value("proj_type", ProjEnum.NORMAL)
        )

        self.__restore_splitter_sizes()

    @property
    def is_3d(self) -> bool:
        return self.parameter.child("proj_setting", "proj_type").value() == ProjEnum.O3D

    def proj_type_changed(self, param: Parameter, new_value: str):
        if self.is_3d:
            self.o3d_widget.show()
        else:
            self.o3d_widget.hide()
        self.settings.setValue("proj_type", new_value)

    def _load_file_3d_callback(self):
        if not self.is_3d:
            return

        img_path = self.filename
        if not self.proj_manager.is_3d_data(img_path):
            notification("3D 视图提示", "当前图片不是3D数据，无法显示3D视图", ToastPreset.WARNING)
            return

        gray_img_path = self.proj_manager.get_gray_img_path(img_path)
        depth_img_path = self.proj_manager.get_depth_img_path(img_path)
        self.o3d_widget.display_with_path(gray_img_path, depth_img_path)

    def __store_splitter_sizes(self):
        sizes = self.centralWidget().sizes()
        self.settings.setValue("o3d_widget_splitter_sizes", sizes, )

    def __restore_splitter_sizes(self):
        sizes = self.settings.value("o3d_widget_splitter_sizes")
        if sizes:
            sizes = int(sizes[0]), int(sizes[1])
            self.centralWidget().setSizes(sizes)

class ProjEnum:
    NORMAL = '常规'
    O3D = '3D'
    # ------------ 3D 视图 end ------------


class ScaleEnum:
    KEEP_PREV_SCALE = '保持上次缩放比例'
    AUTO_SCALE = '自动缩放'
    KEEP_SCALE = '保持缩放比例'