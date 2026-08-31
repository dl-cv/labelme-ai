"""复制 / 粘贴：Ctrl+C 分流、Ctrl+V 偏移/跟随鼠标/裁切。"""

import traceback

from qtpy import QtCore
from qtpy import QtWidgets

from labelme.dlcv import dlcv_tr
from labelme.dlcv.store import STORE
from labelme.dlcv.utils import clip_paste as clip_paste_utils
from labelme.dlcv.utils_func import ToastPreset
from labelme.dlcv.utils_func import notification
from labelme.dlcv.widget.clipboard import clear_copied_shapes
from labelme.dlcv.widget.clipboard import copy_file_to_clipboard
from labelme.dlcv.widget.clipboard import copy_shapes_to_clipboard
from labelme.dlcv.widget.clipboard import paste_shapes_from_clipboard
from labelme.logger import logger


class CopyPasteMixin:
    """挂到 MainWindow：覆盖 copy / paste / duplicate 槽函数。"""

    def copySelectedShape(self):
        """选中多边形时复制多边形；未选中时复制当前图片。"""
        if clip_paste_utils.copy_target_is_shapes(self.canvas.selectedShapes):
            self._copy_selected_shapes_to_clipboard()
        else:
            self.copy_image_to_clipboard()

    def copy_image_to_clipboard(self):
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
            clear_copied_shapes()
            notification(
                dlcv_tr("复制成功"),
                dlcv_tr("图像已复制"),
                ToastPreset.SUCCESS,
            )
        except Exception as e:
            notification(dlcv_tr("复制失败"), str(e), ToastPreset.ERROR)

    def duplicateSelectedShape(self):
        self._copy_selected_shapes_to_clipboard()

    def _copy_selected_shapes_to_clipboard(self):
        if not self.canvas.selectedShapes:
            notification(
                dlcv_tr("提示"), dlcv_tr("请先选中要复制的形状"), ToastPreset.WARNING
            )
            return
        try:
            shapes_data = [
                clip_paste_utils.format_shape_for_clipboard(shape)
                for shape in self.canvas.selectedShapes
            ]
            source_image_path = self.filename
            logger.debug(f"=== DEBUG: 记录源图像路径: {source_image_path} ===")
            copy_shapes_to_clipboard(shapes_data, source_image_path)
            self.actions.paste.setEnabled(True)
            self._same_image_paste_count = 0
            notification(
                dlcv_tr("复制成功"),
                dlcv_tr("多边形已复制"),
                ToastPreset.SUCCESS,
            )
        except Exception as e:
            notification(dlcv_tr("复制失败"), str(e), ToastPreset.ERROR)

    def pasteSelectedShape(self):
        """Ctrl+V：同图累加右下偏移；异图原坐标；可选跟随鼠标；超边裁切。"""
        try:
            shapes_data = paste_shapes_from_clipboard()
            if not shapes_data:
                notification(
                    dlcv_tr("提示"),
                    dlcv_tr("剪贴板中没有可粘贴的内容"),
                    ToastPreset.WARNING,
                )
                return

            shapes = []
            for shape_data in shapes_data:
                shape = clip_paste_utils.create_shape_from_data(shape_data)
                if shape is not None and shape.points:
                    shapes.append(shape)
            if not shapes:
                notification(
                    dlcv_tr("提示"),
                    dlcv_tr("剪贴板中没有可粘贴的内容"),
                    ToastPreset.WARNING,
                )
                return

            source_image_path = shapes_data[0].get("source_image_path")
            same_image = source_image_path == self.filename

            follow_mouse = STORE.paste_follow_mouse
            is_shift_pressed = (
                QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier
            )
            if is_shift_pressed:
                follow_mouse = False

            mouse_xy = None
            if follow_mouse:
                target_pos = self.canvas.prevMovePoint
                mouse_xy = (target_pos.x(), target_pos.y())

            paste_count = getattr(self, "_same_image_paste_count", 0)
            offset = 5
            if same_image and not follow_mouse:
                offset = clip_paste_utils.next_same_image_paste_offset(paste_count + 1)

            kept = clip_paste_utils.apply_paste_transform(
                shapes,
                same_image=same_image,
                follow_mouse=follow_mouse,
                mouse_xy=mouse_xy,
                max_x=self.max_x_width,
                max_y=self.max_y_height,
                offset=offset,
            )
            if not kept:
                notification(
                    dlcv_tr("提示"),
                    dlcv_tr("粘贴的形状超出图像边界，已全部裁切"),
                    ToastPreset.WARNING,
                )
                return

            if same_image and not follow_mouse:
                self._same_image_paste_count = paste_count + 1

            self.loadShapes(kept, replace=False)
            self.setDirty()
            self.canvas.selectShapes(kept)
            notification(
                dlcv_tr("粘贴成功"),
                dlcv_tr("已粘贴 {count} 个形状").format(count=len(kept)),
                ToastPreset.SUCCESS,
            )
        except Exception as e:
            traceback.print_exc()
            notification(dlcv_tr("粘贴失败"), str(e), ToastPreset.ERROR)

    def _init_paste_at_original_position_action(self):
        self.paste_at_original_position_action = QtWidgets.QAction(
            dlcv_tr("在原位置粘贴"), self
        )
        self.paste_at_original_position_action.setShortcut("Ctrl+Shift+V")
        self.addAction(self.paste_at_original_position_action)
        self.paste_at_original_position_action.triggered.connect(self.pasteSelectedShape)
