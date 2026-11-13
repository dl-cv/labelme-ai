import traceback
from typing import List
import math

from labelme.dlcv.store import STORE
from labelme.dlcv.shape_render import ShapeRenderSettings
from labelme.shape import *


class ShapeType:
    POLYGON = "polygon"
    RECTANGLE = "rectangle"
    POINT = "point"
    LINE = "line"
    CIRCLE = "circle"
    LINESTRIP = "linestrip"
    POINTS = "points"
    MASK = "mask"
    ROTATION = "rotation"

    @classmethod
    def all(cls):
        return [
            cls.POLYGON,
            cls.RECTANGLE,
            cls.POINT,
            cls.LINE,
            cls.CIRCLE,
            cls.LINESTRIP,
            cls.POINTS,
            cls.MASK,
            cls.ROTATION,
        ]

    @classmethod
    def can_display_label(cls, shape_type):
        return shape_type in [
            cls.POLYGON,
            cls.RECTANGLE,
            cls.CIRCLE,
            cls.LINESTRIP,
            cls.POINT,
            cls.LINE,
            cls.ROTATION,
        ]

    @classmethod
    def is_geometric(cls, shape_type):
        return shape_type in [
            cls.POLYGON,
            cls.RECTANGLE,
            cls.CIRCLE,
            cls.ROTATION,
        ]

    @classmethod
    def fromShapeData(cls, shape_data):
        shape = super().fromShapeData(shape_data)
        
        # 如果是旋转框，设置direction属性
        if shape.shape_type == ShapeType.ROTATION and "direction" in shape_data:
            shape.direction = shape_data["direction"]
        elif shape.shape_type == ShapeType.ROTATION:
            # 如果没有direction属性，设置默认值
            shape.direction = 0.0
            
        return shape


class Shape(Shape):
    points: List[QtCore.QPointF]

    def __init__(
        self,
        label=None,
        line_color=None,
        shape_type=None,
        flags=None,
        group_id=None,
        description=None,
        mask=None,
        direction=0.0,
        points: List[QtCore.QPointF] | List[List[float]]=None,
        **kwargs,
    ):
        super().__init__(
            label=label,
            line_color=line_color,
            shape_type=shape_type,
            flags=flags,
            group_id=group_id,
            description=description,
            mask=mask,
        )
        self.direction = direction
        # 用于记录旋转框的箭头位置和角度数字位置，用于命中检测
        self.arrow_center = None  # 箭头中心点
        self.arrow_end = None     # 箭头终点
        self.angle_text_rect = None  # 角度数字区域

        if points is not None:
            for point in points:
                if isinstance(point, list):
                    self.addPoint(QtCore.QPointF(*point))
                else:
                    self.addPoint(point)
            self.close()

    def addPoint(self, point: QtCore.QPointF, label=1):
        if self.points and point == self.points[0]:
            self.close()
        else:
            # 检查是否是重复的点（与列表中最后一个点相同）, 防止用户连续点击同一位置时，重复的是最近添加的点
            if self.points:
                last_point = self.points[-1]
                if abs(point.x() - last_point.x()) < 1e-6 and abs(point.y() - last_point.y()) < 1e-6:
                    return  # 重复点，直接返回不添加

            self.points.append(point)
            self.point_labels.append(label)

    def paint(self, painter, settings=None):
        if self.mask is None and not self.points:
            return
        if settings is None:
            settings = ShapeRenderSettings.from_store(self.scale, painter, STORE)

        color = self.select_line_color if self.selected else self.line_color
        pen = QtGui.QPen(color)
        # Try using integer sizes for smoother drawing(?)
        pen.setWidth(self.PEN_WIDTH)
        painter.setPen(pen)

        if self.mask is not None:
            image_to_draw = np.zeros(self.mask.shape + (4,), dtype=np.uint8)
            fill_color = (
                self.select_fill_color.getRgb()
                if self.selected
                else self.fill_color.getRgb()
            )
            image_to_draw[self.mask] = fill_color
            qimage = QtGui.QImage.fromData(labelme.utils.img_arr_to_data(image_to_draw))
            qimage = qimage.scaled(
                qimage.size() * self.scale,
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )

            painter.drawImage(self._scale_point(point=self.points[0]), qimage)

            line_path = QtGui.QPainterPath()
            contours = skimage.measure.find_contours(np.pad(self.mask, pad_width=1))
            for contour in contours:
                contour += [self.points[0].y(), self.points[0].x()]
                line_path.moveTo(
                    self._scale_point(QtCore.QPointF(contour[0, 1], contour[0, 0]))
                )
                for point in contour[1:]:
                    line_path.lineTo(
                        self._scale_point(QtCore.QPointF(point[1], point[0]))
                    )
            painter.drawPath(line_path)

        if self.points:
            line_path = QtGui.QPainterPath()
            vrtx_path = QtGui.QPainterPath()
            negative_vrtx_path = QtGui.QPainterPath()
            center_cross_path = QtGui.QPainterPath()

            if self.shape_type in ["rectangle", "mask"]:
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    rectangle = QtCore.QRectF(
                        self._scale_point(self.points[0]),
                        self._scale_point(self.points[1]),
                    )
                    line_path.addRect(rectangle)
                if self.shape_type == "rectangle":
                    for i in range(len(self.points)):
                        self.drawVertex(vrtx_path, i)
            elif self.shape_type == "rotation":
                # 旋转框绘制（四边与顶点）
                if len(self.points) < 4:
                    return

                # 边框
                line_path.moveTo(self._scale_point(self.points[0]))
                for i in range(1, 5):
                    line_path.lineTo(self._scale_point(self.points[i % 4]))

                # 顶点
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)

                # 箭头
                if settings.canvas_display_rotation_arrow:
                    start, end, p1, p2 = self._rotation_arrow_points()
                    self.arrow_center, self.arrow_end = start, end
                    arrow_pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
                    arrow_pen.setWidth(self.PEN_WIDTH)
                    painter.setPen(arrow_pen)
                    painter.drawLine(self._scale_point(start), self._scale_point(end))
                    painter.drawLine(self._scale_point(end), self._scale_point(p1))
                    painter.drawLine(self._scale_point(end), self._scale_point(p2))

                # 恢复画笔
                painter.setPen(pen)
            
            elif self.shape_type == "circle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    raidus = labelme.utils.distance(
                        self._scale_point(self.points[0] - self.points[1])
                    )
                    line_path.addEllipse(
                        self._scale_point(self.points[0]), raidus, raidus
                    )
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "linestrip":
                line_path.moveTo(self._scale_point(self.points[0]))
                for i, p in enumerate(self.points):
                    line_path.lineTo(self._scale_point(p))
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "points":
                assert len(self.points) == len(self.point_labels)
                for i, point_label in enumerate(self.point_labels):
                    if point_label == 1:
                        self.drawVertex(vrtx_path, i)
                    else:
                        self.drawVertex(negative_vrtx_path, i)
            elif self.shape_type == "point":
                # 点标注：根据设置决定绘制圆形或十字
                if settings.canvas_points_to_crosshair and len(self.points) > 0:
                    # 绘制十字线
                    point = self._scale_point(self.points[0])
                    d = self.point_size
                    line_path.moveTo(point.x() - d / 2, point.y())
                    line_path.lineTo(point.x() + d / 2, point.y())
                    line_path.moveTo(point.x(), point.y() - d / 2)
                    line_path.lineTo(point.x(), point.y() + d / 2)
                else:
                    # 绘制圆形（默认）
                    self.drawVertex(vrtx_path, 0)
            else:
                line_path.moveTo(self._scale_point(self.points[0]))
                # Uncommenting the following line will draw 2 paths
                # for the 1st vertex, and make it non-filled, which
                # may be desirable.
                # self.drawVertex(vrtx_path, 0)

                for i, p in enumerate(self.points):
                    line_path.lineTo(self._scale_point(p))
                    self.drawVertex(vrtx_path, i)
                if self.isClosed():
                    line_path.lineTo(self._scale_point(self.points[0]))

            painter.drawPath(line_path)

            if settings.canvas_display_shape_center_cross:
                center = self.get_center_point()
                if center is not None:
                    scaled_center = self._scale_point(center)
                    half = settings.canvas_shape_center_cross_length / 2.0
                    center_cross_path.moveTo(scaled_center.x() - half, scaled_center.y())
                    center_cross_path.lineTo(scaled_center.x() + half, scaled_center.y())
                    center_cross_path.moveTo(scaled_center.x(), scaled_center.y() - half)
                    center_cross_path.lineTo(scaled_center.x(), scaled_center.y() + half)
                    painter.drawPath(center_cross_path)

            # extra 显示顶点
            if settings.canvas_highlight_start_point:
                # 第一个顶点显示为红色，第二个顶点显示为蓝色，其他顶点使用原来的颜色
                if len(self.points) >= 1:
                    # 绘制第一个顶点（红色）
                    pen.setColor(QtGui.QColor(255, 0, 0, 255))  # 红色
                    painter.setPen(pen)
                    first_vertex_path = QtGui.QPainterPath()
                    self.drawVertex(first_vertex_path, 0)
                    painter.drawPath(first_vertex_path)
                    painter.fillPath(first_vertex_path, QtGui.QColor(255, 0, 0, 255))

                if len(self.points) >= 2:
                    # 绘制第二个顶点（蓝色）
                    pen.setColor(QtGui.QColor(0, 0, 255, 255))  # 蓝色
                    painter.setPen(pen)
                    second_vertex_path = QtGui.QPainterPath()
                    self.drawVertex(second_vertex_path, 1)
                    painter.drawPath(second_vertex_path)
                    painter.fillPath(second_vertex_path, QtGui.QColor(0, 0, 255, 255))

                # 绘制其他顶点（使用原来的颜色）
                if len(self.points) > 2:
                    pen.setColor(self.line_color)
                    painter.setPen(pen)
                    other_vertices_path = QtGui.QPainterPath()
                    for i in range(2, len(self.points)):
                        self.drawVertex(other_vertices_path, i)
                    painter.drawPath(other_vertices_path)
                    painter.fillPath(other_vertices_path, self._vertex_fill_color)

            elif vrtx_path.length() > 0:
                painter.drawPath(vrtx_path)
                painter.fillPath(vrtx_path, self._vertex_fill_color)
            # extra end

            if self.fill and self.mask is None and self.isFillable():
                color = self.select_fill_color if self.selected else self.fill_color
                painter.fillPath(line_path, color)

            # extra 显示标签
            try:
                if (
                    ShapeType.can_display_label(self.shape_type)
                    and self.label
                    and settings.canvas_display_shape_label
                ):
                    bg_rect = self._label_paint_rect(self.scale, settings)
                    painter.fillRect(bg_rect, QtGui.QColor(30, 31, 34, int(255 * 0.7)))
                    painter.setPen(QtGui.QColor(105, 170, 88))
                    previous_font = painter.font()
                    painter.setFont(settings.label_font)
                    try:
                        painter.drawText(bg_rect, QtCore.Qt.AlignCenter, self.label)
                    finally:
                        painter.setFont(previous_font)
            except:
                pass
            # extra end

            pen.setColor(QtGui.QColor(255, 0, 0, 255))
            painter.setPen(pen)
            painter.drawPath(negative_vrtx_path)
            painter.fillPath(negative_vrtx_path, QtGui.QColor(255, 0, 0, 255))

    def _rotation_arrow_points(self):
        """Share arrow geometry; a value signature also catches direct point edits."""
        key = (self.direction, tuple((point.x(), point.y()) for point in self.points))
        cached = getattr(self, "_rotation_arrow_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        cx = sum(point.x() for point in self.points) / 4.0
        cy = sum(point.y() for point in self.points) / 4.0
        angle = math.radians(self.direction)
        dx, dy = math.cos(angle), math.sin(angle)
        best_score = best_length = 0.0
        for i in range(4):
            start, end = self.points[i], self.points[(i + 1) % 4]
            ex, ey = end.x() - start.x(), end.y() - start.y()
            length = math.hypot(ex, ey)
            if length:
                score = abs((ex * dx + ey * dy) / length)
                if score > best_score:
                    best_score, best_length = score, length
        arrow_length = max(12.0, best_length * 0.2)
        start = QtCore.QPointF(cx + dx * best_length * 0.5,
                              cy + dy * best_length * 0.5)
        end = QtCore.QPointF(start.x() + dx * arrow_length,
                            start.y() + dy * arrow_length)
        heads = []
        for offset in (150, -150):
            head_angle = math.radians(self.direction + offset)
            heads.append(QtCore.QPointF(
                end.x() + arrow_length * 0.2 * math.cos(head_angle),
                end.y() + arrow_length * 0.2 * math.sin(head_angle),
            ))
        points = (start, end, heads[0], heads[1])
        self._rotation_arrow_cache = (key, points)
        return points

    def _label_paint_rect(self, scale, settings, font_metrics=None):
        metrics = font_metrics if font_metrics is not None else settings.label_font_metrics
        position = settings.canvas_shape_label_position
        anchor = self.get_label_paint_point(position)
        anchor = QtCore.QPointF(anchor.x() * scale, anchor.y() * scale)
        size = settings.label_sizes.get(self.label) if font_metrics is None else None
        if size is None:
            size = (metrics.horizontalAdvance(self.label) + 10, metrics.height() + 10)
            if font_metrics is None:
                settings.label_sizes[self.label] = size
        rect = QtCore.QRectF(0, 0, *size)
        if position == "top_left":
            rect.moveTopLeft(anchor)
        elif position == "bottom_right":
            rect.moveBottomRight(anchor)
        else:
            rect.moveCenter(anchor)
        return rect

    def paintBounds(self, scale, settings=None, font_metrics=None):
        """Conservative bounds in painter-logical pixels, before canvas offset.

        The caller must use the same scale/settings as for painting. Points are
        intentionally read on every call: editors also replace/mutate them
        directly, so a persistent bounds cache would become stale. Padding
        includes the largest normal vertex highlight and raster/pen coverage.
        """
        if not self.points:
            return QtCore.QRectF()
        if settings is None:
            settings = ShapeRenderSettings.from_store(scale, store=STORE)
        xs = [point.x() * scale for point in self.points]
        ys = [point.y() * scale for point in self.points]
        left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
        if self.shape_type == ShapeType.CIRCLE and len(self.points) >= 2:
            radius = math.hypot(xs[1] - xs[0], ys[1] - ys[0])
            left, right = min(left, xs[0] - radius), max(right, xs[0] + radius)
            top, bottom = min(top, ys[0] - radius), max(bottom, ys[0] + radius)
        if self.mask is not None:
            height, width = self.mask.shape[:2]
            # find_contours pads the mask, so include its outer padded edge.
            left, top = min(left, xs[0] - scale), min(top, ys[0] - scale)
            right = max(right, xs[0] + (width + 1) * scale)
            bottom = max(bottom, ys[0] + (height + 1) * scale)
        pen_padding = abs(self.PEN_WIDTH) * 2 + 2
        vertex_padding = abs(self.point_size) * 2
        padding = vertex_padding + pen_padding
        bounds = QtCore.QRectF(left - padding, top - padding,
                              right - left + padding * 2, bottom - top + padding * 2)
        if (self.shape_type == ShapeType.ROTATION and len(self.points) >= 4
                and settings.canvas_display_rotation_arrow):
            # 任意边长不超过包围盒对角线。用保守半径覆盖箭身/箭头，
            # 屏幕外的框无需再逐边匹配方向或创建箭头路径。
            diagonal = math.hypot(right - left, bottom - top)
            reach = diagonal * 0.5 + 1.2 * max(12 * scale, diagonal * 0.2) + pen_padding
            cx, cy = sum(xs) / 4, sum(ys) / 4
            bounds = bounds.united(QtCore.QRectF(cx - reach, cy - reach,
                                                 reach * 2, reach * 2))
        if settings.canvas_display_shape_center_cross:
            center = self.get_center_point()
            if center is not None:
                half = abs(settings.canvas_shape_center_cross_length) / 2 + pen_padding
                cross_bounds = QtCore.QRectF(center.x() * scale - half,
                                            center.y() * scale - half, half * 2, half * 2)
                bounds = bounds.united(cross_bounds)
        if (settings.canvas_display_shape_label and self.label
                and ShapeType.can_display_label(self.shape_type)):
            try:
                label_bounds = self._label_paint_rect(scale, settings, font_metrics)
            except (ValueError, TypeError, AttributeError):
                # Malformed in-progress polygons also skip labels in paint().
                pass
            else:
                bounds = bounds.united(label_bounds.adjusted(-2, -2, 2, 2))
        return bounds

    # extra methods

    """额外函数"""

    def clear_points(self):
        while self.points:
            self.points.pop()

    # 获取中心点， 用于绘制标签；点数不足时返回 None
    def get_center_point(self) -> QtCore.QPointF | None:
        if not self.points:
            return None
        if self.shape_type == ShapeType.RECTANGLE:
            if len(self.points) < 2:
                return None
            center_x = (self.points[0].x() + self.points[1].x()) / 2
            center_y = (self.points[0].y() + self.points[1].y()) / 2
            return QtCore.QPointF(center_x, center_y)
        elif self.shape_type == ShapeType.CIRCLE:
            return self.points[0]
        elif self.shape_type == ShapeType.ROTATION:
            # 计算旋转框的中心点
            if len(self.points) >= 4:
                # 如果有4个点，计算这4个点的中心
                center_x = sum(p.x() for p in self.points) / len(self.points)
                center_y = sum(p.y() for p in self.points) / len(self.points)
                return QtCore.QPointF(center_x, center_y)
            # 点数不足时不画中心
            return None
        elif self.shape_type == ShapeType.POLYGON:
            # 计算多边形的中心点
            points = self.points
            x_val = [point.x() for point in points]
            y_val = [point.y() for point in points]

            x_min = min(x_val)
            x_max = max(x_val)
            y_min = min(y_val)
            y_max = max(y_val)

            x = (x_min + x_max) / 2
            y = (y_min + y_max) / 2
            return QtCore.QPointF(x, y)
        elif self.shape_type == ShapeType.LINESTRIP:
            return self.points[len(self.points) // 2]
        elif self.shape_type == ShapeType.LINE:
            if len(self.points) < 2:
                return None
            x1, y1 = self.points[0].x(), self.points[0].y()
            x2, y2 = self.points[1].x(), self.points[1].y()
            return QtCore.QPointF((x1 + x2) / 2, (y1 + y2) / 2)
        else:
            return self.points[0]

    # 获取标签绘制点， 用于绘制标签
    def get_label_paint_point(self, position=None) -> QtCore.QPointF:
        if position is None:
            position = getattr(STORE, 'canvas_shape_label_position', 'center')

        # 计算形状的边界框
        if self.points:
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
        else:
            return self.get_center_point()

        if position == 'top_left':
            return QtCore.QPointF(x_min, y_min)
        elif position == 'bottom_right':
            return QtCore.QPointF(x_max, y_max)

        # center 默认逻辑
        center_point = self.get_center_point()

        if self.shape_type == ShapeType.POLYGON:
            import shapely
            from shapely.geometry import Polygon

            geo_polygon = Polygon([(point.x(), point.y()) for point in self.points])

            if geo_polygon.contains(
                shapely.geometry.Point(center_point.x(), center_point.y())
            ):
                return center_point
            else:
                geo_point = shapely.geometry.Point(center_point.x(), center_point.y())
                min_distance = float("inf")
                nearest_point = None
                for i in range(len(self.points)):
                    p1 = self.points[i]
                    p2 = self.points[(i + 1) % len(self.points)]
                    geo_line = shapely.geometry.LineString(
                        [(p1.x(), p1.y()), (p2.x(), p2.y())]
                    )
                    distance = geo_line.distance(geo_point)
                    if distance < min_distance:
                        min_distance = distance
                        nearest_point = geo_line.interpolate(
                            geo_line.project(geo_point)
                        )
                return QtCore.QPointF(nearest_point.x, nearest_point.y)
        elif self.shape_type == ShapeType.ROTATION:
            return center_point
        else:
            return center_point

    def get_points_pos(self) -> List[List[float]]:
        """返回一个所有点的坐标的二维列表"""
        pos_list = []
        for point in self.points:
            x, y = point.x(), point.y()
            pos_list.append([x, y])
        return pos_list

    def convert_to_polygon(self):
        """将当前的 Shape 对象转换为多边形的形式"""
        from labelme.dlcv.utils.shape import shape_to_points

        points = shape_to_points(self).tolist()
        self.points = []
        for point in points:
            self.addPoint(QtCore.QPointF(*point))

        self.shape_type = ShapeType.POLYGON

    def format_shape(self, shape):
        """格式化shape，确保包含direction属性"""
        data = shape.other_data.copy()
        data.update(
            dict(
                label=shape.label.encode("utf-8") if PY2 else shape.label,
                points=[(p.x(), p.y()) for p in shape.points],
                group_id=shape.group_id,
                description=shape.description,
                shape_type=shape.shape_type,
                flags=shape.flags,
                mask=(
                    None
                    if shape.mask is None
                    else utils.img_arr_to_b64(shape.mask.astype(np.uint8))
                ),
            )
        )
        
        # 如果是旋转框，添加direction属性
        if shape.shape_type == "rotation":
            # 确保direction值是浮点数且在0-360度之间
            direction = float(getattr(shape, "direction", 0.0)) % 360
            data["direction"] = direction
            
        return data

    def isFillable(self):
        """Returns whether the shape is fillable or not."""
        return self.shape_type in [ShapeType.POLYGON, ShapeType.ROTATION, ShapeType.RECTANGLE]

    # 增加检测方法
    def isArrowHit(self, point, epsilon=None):
        """检测是否点击在红色方向箭头上（严格检测：必须精确命中箭头和箭身）"""
        # 如果关闭了箭头显示，不允许拖拽箭头
        if not getattr(STORE, 'canvas_display_rotation_arrow', True):
            return False
            
        if self.shape_type != "rotation":
            return False
            
        # 使用严格的容差：如果未指定epsilon，使用线宽的一半（更严格）
        if epsilon is None:
            # 使用线宽的一半作为容差，确保只有真正在线段上的点才算命中
            epsilon = max(1.0, self.PEN_WIDTH / 2.0)
        else:
            # 如果指定了epsilon，使用更小的值确保严格检测
            epsilon = min(epsilon, max(1.0, self.PEN_WIDTH / 2.0))
            
        if len(self.points) < 4:
            return False
        # 屏幕外的框不再每帧重画，命中不能依赖上次paint留下的端点。
        start_point, end_point, p1, p2 = self._rotation_arrow_points()
        self.arrow_center, self.arrow_end = start_point, end_point
        
        # 辅助函数：严格检查点是否在线段上（使用严格的容差）
        def isPointOnLineSegment(point, line_start, line_end, tolerance):
            """严格检查点是否在线段上，考虑容差"""
            line = QtCore.QLineF(line_start, line_end)
            len_line = line.length()
            
            if len_line == 0:
                # 线段长度为0，检查点是否在起点/终点附近
                return QtCore.QLineF(point, line_start).length() < tolerance
            
            # 计算点到线段的投影
            t = ((point.x() - line_start.x()) * (line_end.x() - line_start.x()) + 
                 (point.y() - line_start.y()) * (line_end.y() - line_start.y())) / (len_line * len_line)
                 
            # 严格检查：投影必须在线段范围内（0到1之间，包含端点）
            if t < 0 or t > 1:
                # 点的投影在线段之外，不算命中
                return False
                
            # 点的投影在线段上，计算精确距离
            px = line_start.x() + t * (line_end.x() - line_start.x())
            py = line_start.y() + t * (line_end.y() - line_start.y())
            dist = QtCore.QLineF(point, QtCore.QPointF(px, py)).length()
            
            # 严格检查：距离必须小于容差才算命中
            return dist < tolerance
        
        # 严格检查：必须命中箭头主线段或箭头头部才算选中
        # 检查是否在主线段上（从start到end，这是红色箭头的主线段）
        if isPointOnLineSegment(point, start_point, end_point, epsilon):
            return True
        
        # 检查是否在箭头头部左线上（从end到p1）
        if isPointOnLineSegment(point, end_point, p1, epsilon):
            return True
        
        # 检查是否在箭头头部右线上（从end到p2）
        if isPointOnLineSegment(point, end_point, p2, epsilon):
            return True
        
        # 严格规则：点在箭头周围都不算命中
        return False
        
    def isAngleTextHit(self, point):
        """检测是否点击在角度数字上"""
        # 角度文本已被移除，始终返回False
        return False
