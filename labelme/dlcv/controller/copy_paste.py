"""Ctrl+C 和 Ctrl+V 的多边形复制粘贴逻辑。"""

from labelme.dlcv import dlcv_tr
from labelme.dlcv.store import STORE
from labelme.dlcv.utils import copy_paste as copy_paste_utils
from labelme.dlcv.utils_func import ToastPreset
from labelme.dlcv.utils_func import notification
from labelme.dlcv.widget.clipboard import copy_file_to_clipboard
from labelme.logger import logger


class CopyPasteMixin:
    """为主窗口提供图片复制、多边形复制和多边形粘贴。"""

    def copySelectedShape(self):
        selected_polygons = self._selected_polygons()
        if selected_polygons:
            self._copy_selected_shapes(selected_polygons)
        else:
            self.copy_image_to_clipboard()

    def _selected_polygons(self):
        selected = []
        selected_ids = set()

        def add(shape):
            if shape is None or id(shape) in selected_ids:
                return
            selected_ids.add(id(shape))
            selected.append(shape)

        for shape in getattr(self.canvas, "selectedShapes", ()):
            add(shape)
        for shape in getattr(self.canvas, "shapes", ()):
            if getattr(shape, "selected", False):
                add(shape)
        label_list = getattr(self, "labelList", None)
        if label_list is not None:
            for item in label_list.selectedItems():
                add(item.shape())

        return [shape for shape in selected if shape.shape_type == "polygon"]

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
        except Exception as exc:
            logger.exception("复制图像失败")
            notification(dlcv_tr("复制失败"), str(exc), ToastPreset.ERROR)
            return

        self._copied_shapes = None
        self._copied_shapes_source = ""
        self._same_image_paste_count = 0
        self.actions.paste.setEnabled(False)
        notification(
            dlcv_tr("复制成功"),
            dlcv_tr("图像已复制"),
            ToastPreset.SUCCESS,
        )

    def _copy_selected_shapes(self, selected_shapes):
        shapes = [shape.copy() for shape in selected_shapes]
        try:
            copy_paste_utils.validate_shapes(shapes)
        except copy_paste_utils.CopyPasteError:
            self._copied_shapes = None
            self._copied_shapes_source = ""
            self._same_image_paste_count = 0
            self.actions.paste.setEnabled(False)
            notification(
                dlcv_tr("复制失败"),
                dlcv_tr("选中的多边形非法，无法复制"),
                ToastPreset.WARNING,
            )
            return

        for shape in shapes:
            shape.selected = False
        source_path = getattr(self, "imagePath", None) or getattr(
            self, "filename", None
        )
        self._copied_shapes = shapes
        self._copied_shapes_source = copy_paste_utils.normalize_image_path(source_path)
        self._same_image_paste_count = 0
        self.actions.paste.setEnabled(True)
        notification(
            dlcv_tr("复制成功"),
            dlcv_tr("多边形已复制"),
            ToastPreset.SUCCESS,
        )

    def pasteSelectedShape(self):
        if not self._copied_shapes:
            notification(
                dlcv_tr("提示"),
                dlcv_tr("没有可粘贴的多边形"),
                ToastPreset.WARNING,
            )
            return

        shapes = [shape.copy() for shape in self._copied_shapes]
        target_path = getattr(self, "imagePath", None) or getattr(
            self, "filename", None
        )
        same_image = copy_paste_utils.is_same_image(
            self._copied_shapes_source,
            target_path,
        )
        follow_cursor = bool(STORE.paste_follow_mouse)
        cursor_xy = None
        if follow_cursor:
            cursor = getattr(self.canvas, "prevMovePoint", None)
            if cursor is not None:
                cursor_xy = (cursor.x(), cursor.y())

        paste_count = getattr(self, "_same_image_paste_count", 0)
        offset = 10.0 * (paste_count + 1) if same_image and not follow_cursor else 0.0
        try:
            dx, dy = copy_paste_utils.placement_translation(
                shapes,
                same_image=same_image,
                follow_cursor=follow_cursor,
                cursor_xy=cursor_xy,
                max_x=self.max_x_width,
                max_y=self.max_y_height,
                offset=offset,
            )
            copy_paste_utils.translate_shapes(shapes, dx, dy)
            copy_paste_utils.validate_shapes(shapes)
        except copy_paste_utils.CopyPasteError as exc:
            self._notify_copy_paste_error(exc.code)
            return

        if same_image and not follow_cursor:
            self._same_image_paste_count = paste_count + 1
        self.loadShapes(shapes, replace=False)
        self.setDirty()
        self.canvas.selectShapes(shapes)
        notification(
            dlcv_tr("粘贴成功"),
            dlcv_tr("多边形已粘贴"),
            ToastPreset.SUCCESS,
        )

    def prepare_polygons_for_save(self):
        moved = False
        for shape in self.canvas.shapes:
            if shape.shape_type != "polygon":
                continue
            try:
                dx, dy = copy_paste_utils.move_shape_inside_image(
                    shape,
                    max_x=self.max_x_width,
                    max_y=self.max_y_height,
                )
            except copy_paste_utils.CopyPasteError as exc:
                self.canvas.selectShapes([shape])
                self._notify_copy_paste_error(exc.code, saving=True)
                return False
            moved = moved or bool(dx or dy)

        if moved:
            self.canvas.storeShapes()
            self.canvas.update()
        self.refresh_invalid_polygon_state()
        return True

    def _notify_copy_paste_error(self, code, saving=False):
        if code == "too_large":
            message = dlcv_tr("当前图像无法包含该多边形")
        elif code == "cannot_offset":
            message = dlcv_tr("图像内没有足够空间错开多边形")
        elif code in ("image_missing", "cursor_missing"):
            message = dlcv_tr("无法确定多边形的粘贴位置")
        else:
            message = dlcv_tr(
                "多边形非法，无法保存" if saving else "多边形非法，无法粘贴"
            )
        notification(
            dlcv_tr("保存失败" if saving else "粘贴失败"),
            message,
            ToastPreset.WARNING,
        )
