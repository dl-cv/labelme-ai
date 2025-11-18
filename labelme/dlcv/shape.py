import traceback
from typing import List
import math

from labelme.dlcv.store import STORE
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
        super().addPoint(point, label)

    def paint(self, painter):
        if self.mask is None and not self.points:
            return

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
                if getattr(STORE, 'canvas_display_rotation_arrow', True):
                    cx = sum(p.x() for p in self.points) / 4.0
                    cy = sum(p.y() for p in self.points) / 4.0
                    center = QtCore.QPointF(cx, cy)
                    angle = math.radians(self.direction)
                    dir_vec = QtCore.QPointF(math.cos(angle), math.sin(angle))

                    # 找与方向最平行的边来确定尺度
                    def _edge(i):
                        j = (i + 1) % 4
                        return QtCore.QPointF(
                            self.points[j].x() - self.points[i].x(),
                            self.points[j].y() - self.points[i].y(),
                        )

                    def _len(v):
                        return math.hypot(v.x(), v.y())

                    def _dot(u, v):
                        return u.x() * v.x() + u.y() * v.y()

                    best = 0.0
                    best_len = 0.0
                    for i in range(4):
                        e = _edge(i)
                        L = _len(e)
                        if L > 0:
                            score = abs(_dot(QtCore.QPointF(e.x() / L, e.y() / L), dir_vec))
                            if score > best:
                                best = score
                                best_len = L

                    arrow_len = max(12.0, best_len * 0.2)
                    start = QtCore.QPointF(
                        center.x() + dir_vec.x() * (best_len * 0.5),
                        center.y() + dir_vec.y() * (best_len * 0.5),
                    )
                    end = QtCore.QPointF(
                        start.x() + dir_vec.x() * arrow_len,
                        start.y() + dir_vec.y() * arrow_len,
                    )

                    self.arrow_center, self.arrow_end = start, end

                    arrow_pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
                    arrow_pen.setWidth(self.PEN_WIDTH)
                    painter.setPen(arrow_pen)
                    painter.drawLine(self._scale_point(start), self._scale_point(end))

                    # 箭头头部
                    head_len = arrow_len * 0.2
                    h1 = math.radians(self.direction + 150)
                    h2 = math.radians(self.direction - 150)
                    p1 = QtCore.QPointF(end.x() + head_len * math.cos(h1),
                                        end.y() + head_len * math.sin(h1))
                    p2 = QtCore.QPointF(end.x() + head_len * math.cos(h2),
                                        end.y() + head_len * math.sin(h2))
                    painter.drawLine(self._scale_point(end), self._scale_point(p1))
                    painter.drawLine(self._scale_point(end), self._scale_point(p2))

                # 恢复画笔
                painter.setPen(pen)
            
                # 显示Label（如果有）- 优化旋转框标签显示
                if self.label and getattr(STORE, 'canvas_display_rotation_label', True):
                    try:
                        # 之前没有对字体进行缩放， 现在对字体进行中心缩放
                        label = self.label
                        center = self.get_label_paint_point()
                        scaled_center = self._scale_point(center)
            
                        # 设置粗体
                        font = painter.font()
                        font.setBold(True)
            
                        # 绘制标签时，从store中读取标签字体大小
                        font.setPointSize(STORE.canvas_shape_label_font_size if self.scale < 1 else int(STORE.canvas_shape_label_font_size * self.scale))
                        painter.setFont(font)
            
                        # 计算矩形宽度
                        padding = 5
                        text_width = painter.fontMetrics().width(label)
                        text_height = painter.fontMetrics().height()
                        bg_rect = QtCore.QRectF(scaled_center, scaled_center)
                        bg_rect.setWidth(text_width + padding * 2)
                        bg_rect.setHeight(text_height + padding * 2)
                        bg_rect.moveCenter(scaled_center)
            
                        # 绘制背景 - 增加透明度
                        painter.fillRect(bg_rect, QtGui.QColor(30, 31, 34, int(255 * 0.8)))
            
                        # 设置字体颜色
                        font_color = QtGui.QColor(105, 170, 88)
                        painter.setPen(font_color)
                        painter.drawText(bg_rect, QtCore.Qt.AlignCenter, label)
            
                        # 恢复原来的画笔
                        painter.setPen(pen)
                    except Exception as e:
                        # 记录错误但不打印堆栈跟踪
                        print(f"显示旋转框标签出错: {e}")
                        pass
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
                if STORE.canvas_points_to_crosshair and len(self.points) > 0:
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

            # extra 显示顶点
            if STORE.canvas_highlight_start_point:
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

            if self.fill and self.mask is None:
                color = self.select_fill_color if self.selected else self.fill_color
                painter.fillPath(line_path, color)

            # extra 显示标签
            try:
                # 旋转框使用自己的标签绘制逻辑，跳过通用绘制
                if self.shape_type == "rotation":
                    pass
                elif (
                    ShapeType.can_display_label(self.shape_type)
                    and self.label
                    and STORE.canvas_display_shape_label
                ):
                    label = self.label
                    center = self.get_label_paint_point()
                    scaled_center = self._scale_point(center)

                    # 设置粗体
                    font = painter.font()
                    font.setBold(True)

                    # 绘制标签时，从store中读取标签字体大小
                    font.setPointSize(STORE.canvas_shape_label_font_size if self.scale < 1 else int(STORE.canvas_shape_label_font_size * self.scale))
                    painter.setFont(font)

                    # 计算矩形宽度
                    padding = 5
                    text_width = painter.fontMetrics().width(label)
                    text_height = painter.fontMetrics().height()
                    bg_rect = QtCore.QRectF(scaled_center, scaled_center)
                    bg_rect.setWidth(text_width + padding * 2)
                    bg_rect.setHeight(text_height + padding * 2)
                    bg_rect.moveCenter(scaled_center)

                    painter.fillRect(bg_rect, QtGui.QColor(30, 31, 34, int(255 * 0.7)))

                    # 设置字体颜色
                    font_color = QtGui.QColor(105, 170, 88)
                    painter.setPen(font_color)
                    painter.drawText(bg_rect, QtCore.Qt.AlignCenter, label)
            except:
                pass
            # extra end

            pen.setColor(QtGui.QColor(255, 0, 0, 255))
            painter.setPen(pen)
            painter.drawPath(negative_vrtx_path)
            painter.fillPath(negative_vrtx_path, QtGui.QColor(255, 0, 0, 255))

    # extra methods

    """额外函数"""

    def clear_points(self):
        while self.points:
            self.points.pop()

    # 获取中心点， 用于绘制标签
    def get_center_point(self) -> QtCore.QPointF:
        if self.shape_type == ShapeType.RECTANGLE:
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
            elif len(self.points) > 0:
                # 如果点数不足但至少有一个点，返回第一个点
                return self.points[0]
            else:
                # 如果没有点，返回原点
                return QtCore.QPointF(0, 0)
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
            x1, y1 = self.points[0].x(), self.points[0].y()
            x2, y2 = self.points[1].x(), self.points[1].y()
            return QtCore.QPointF((x1 + x2) / 2, (y1 + y2) / 2)
        else:
            return self.points[0]

    # 获取标签绘制点， 用于绘制标签
    def get_label_paint_point(self) -> QtCore.QPointF:
        import shapely
        from shapely.geometry import Polygon

        # 获取中心点
        center_point = self.get_center_point()

        # 如果是多边形， 则需要计算离中心点最近的点
        if self.shape_type == ShapeType.POLYGON:
            geo_polygon = Polygon([(point.x(), point.y()) for point in self.points])

            if geo_polygon.contains(
                shapely.geometry.Point(center_point.x(), center_point.y())
            ):
                return center_point
            else:
                geo_point = shapely.geometry.Point(center_point.x(), center_point.y())
                # 找离中心点最近的边, 并计算垂直距离
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
            # 对于旋转框，直接返回中心点
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
        return self.shape_type in ["polygon", "rectangle", "rotation"]

    # 增加检测方法
    def isArrowHit(self, point, epsilon=10.0):
        """检测是否点击在方向箭头上"""
        # 如果关闭了箭头显示，不允许拖拽箭头
        if not getattr(STORE, 'canvas_display_rotation_arrow', True):
            return False
            
        if self.shape_type != "rotation":
            return False
            
        # 确保必要的属性已经初始化
        if not hasattr(self, 'arrow_center') or not hasattr(self, 'arrow_end') or self.arrow_center is None or self.arrow_end is None:
            # 如果箭头相关属性未初始化，临时计算
            if len(self.points) < 4:
                return False
                
            # 计算中心点
            center_x = sum(p.x() for p in self.points) / 4
            center_y = sum(p.y() for p in self.points) / 4
            center = QtCore.QPointF(center_x, center_y)
            
            # 计算旋转方向向量
            angle_rad = math.radians(self.direction)
            dir_vector = QtCore.QPointF(math.cos(angle_rad), math.sin(angle_rad))
            
            # 计算与箭头方向平行的边的长度
            # 计算各个边的方向向量
            edge_vectors = []
            for i in range(4):
                next_i = (i + 1) % 4
                edge_vec = QtCore.QPointF(
                    self.points[next_i].x() - self.points[i].x(),
                    self.points[next_i].y() - self.points[i].y()
                )
                edge_vectors.append(edge_vec)
            
            # 找出与箭头方向最平行的边
            max_dot_product = -1
            parallel_edge_length = 0
            for edge_vec in edge_vectors:
                # 计算单位向量
                edge_length = math.sqrt(edge_vec.x()**2 + edge_vec.y()**2)
                if edge_length > 0:
                    edge_unit_vec = QtCore.QPointF(edge_vec.x()/edge_length, edge_vec.y()/edge_length)
                    # 计算点积的绝对值（平行度）
                    dot_product = abs(edge_unit_vec.x()*dir_vector.x() + edge_unit_vec.y()*dir_vector.y())
                    if dot_product > max_dot_product:
                        max_dot_product = dot_product
                        parallel_edge_length = edge_length
            
            # 计算箭头起始点：从中心点向箭头方向移动平行边长度的一半
            arrow_start_x = center_x + (dir_vector.x() * parallel_edge_length * 0.5)
            arrow_start_y = center_y + (dir_vector.y() * parallel_edge_length * 0.5)
            arrow_start = QtCore.QPointF(arrow_start_x, arrow_start_y)
            
            # 计算箭头长度：与箭头平行的边的长度的0.3
            arrow_length = parallel_edge_length * 0.3
            
            # 计算箭头终点
            end_x = arrow_start_x + arrow_length * dir_vector.x()
            end_y = arrow_start_y + arrow_length * dir_vector.y()
            arrow_end = QtCore.QPointF(end_x, end_y)
            
            # 临时设置箭头属性
            self.arrow_center = arrow_start
            self.arrow_end = arrow_end
            
        # 增大命中检测区域，使箭头更容易点击
        epsilon = max(epsilon, 10.0)  # 降低最小检测半径从20.0到10.0
            
        # 首先检查点击位置是否在箭头终点附近
        end_point = self.arrow_end
        if QtCore.QLineF(point, end_point).length() < epsilon * 1.2:  # 降低倍数从1.5到1.2
            return True
            
        # 然后检查是否在箭头起点附近
        start_point = self.arrow_center
        if QtCore.QLineF(point, start_point).length() < epsilon * 0.8:  # 缩小起点检测范围
            return True
            
        # 最后检查是否在箭头线段上
        line = QtCore.QLineF(start_point, end_point)
        len_line = line.length()
        
        if len_line == 0:
            return False
            
        # 计算点到线段的投影
        t = ((point.x() - start_point.x()) * (end_point.x() - start_point.x()) + 
             (point.y() - start_point.y()) * (end_point.y() - start_point.y())) / (len_line * len_line)
             
        if t < 0 or t > 1:
            # 点的投影在线段之外
            return False
            
        # 点的投影在线段上，计算距离
        px = start_point.x() + t * (end_point.x() - start_point.x())
        py = start_point.y() + t * (end_point.y() - start_point.y())
        dist = QtCore.QLineF(point, QtCore.QPointF(px, py)).length()
        
        return dist < epsilon
        
    def isAngleTextHit(self, point):
        """检测是否点击在角度数字上"""
        # 角度文本已被移除，始终返回False
        return False
