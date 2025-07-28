from shapely import Polygon, Point, LineString, MultiPolygon
import math  # 添加math模块导入

from labelme.widgets.canvas import *
from labelme.dlcv.shape import ShapeType


class CustomCanvasAttr:
    def __init__(self):
        self.drawing_with_right_btn = False
        self.draw_polygon_with_mousemove = False  # 鼠标移动时绘制多边形
        self.two_points_distance = 30  # 连续绘制点时,两点的距离
        # 画笔功能
        self.brush_enabled = False  # 是否启用画笔
        self.brush_size = 10  # 画笔大小
        self.min_brush_size = 3  # 最小画笔大小
        self.brush_drawing = False  # 是否正在使用画笔绘制
        self.brush_erase_mode = False  # 是否为消除模式（右键）
        self.brush_points = []  # 画笔绘制的点集


from labelme.dlcv.shape import Shape
from labelme.dlcv.store import STORE


class Canvas(Canvas, CustomCanvasAttr):
    current: Shape = None
    # 添加shapeDone信号
    shapeDone = QtCore.Signal()

    def transformPos(self, point):
        """Convert from widget-logical coordinates to painter-logical ones."""
        # 继承父类的基本转换，然后减去画布拖动的偏移量
        transformed = point / self.scale - self.offsetToCenter()
        # 减去画布拖动产生的偏移量
        return transformed - self.offset

    def __init__(self, *args, **kwargs):
        self.epsilon = kwargs.pop("epsilon", 10.0)
        self.double_click = kwargs.pop("double_click", "close")
        if self.double_click not in [None, "close"]:
            raise ValueError(
                "Unexpected value for double_click event: {}".format(self.double_click)
            )
        self.num_backups = kwargs.pop("num_backups", 10)
        # 修复_crosshair字典，添加rotation键
        crosshair_config = kwargs.pop(
            "crosshair",
            {
                "polygon": False,
                "rectangle": True,
                "circle": False,
                "line": False,
                "point": False,
                "linestrip": False,
                "ai_polygon": False,
                "ai_mask": False,
            },
        )
        # 确保crosshair_config中包含rotation键
        if "rotation" not in crosshair_config:
            crosshair_config["rotation"] = True  # 默认为True，显示十字线
            
        self._crosshair = crosshair_config
        super().__init__(*args, **kwargs)
        self.rotation_angle = 0.0  # 旋转框的旋转角度
        
        # 添加箭头拖拽和角度调整功能的变量
        self.draggingArrow = False  # 是否正在拖拽箭头
        self.hArrowShape = None     # 当前命中的箭头所属形状
        
        # 画笔功能变量
        self.brush_points = []      # 画笔绘制的点集
        # 画布拖动相关变量
        self.draggingCanvas = False
        self.canvasDragStart = None
        self.canvasOffsetStart = None
        # 画布偏移初始化
        self.offset = QtCore.QPointF(0, 0)

    # region Mouse Events
    def mouse_left_click(self, ev, pos: QtCore.QPointF):
        is_shift_pressed = ev.modifiers() & QtCore.Qt.ShiftModifier

        if self.drawing():
            if self.current:
                # Add point to existing shape.
                if self.createMode == "polygon":
                    self.current.addPoint(self.line[1])
                    self.line[0] = self.current[-1]
                    if self.current.isClosed():
                        self.finalise()
                elif self.createMode in ["rectangle", "circle", "line", "rotation"]:  # 添加rotation
                    assert len(self.current.points) == 1

                    # extra 标注圆时,圆心和半径是否在图片内
                    if self.createMode == 'circle':
                        # 圆心和半径, 绘制的圆是否在图片内
                        center_point = self.line.points[0]
                        radius = labelme.utils.distance(self.line.points[0] - self.line.points[1])
                        if not self.is_circle_in_image(center_point, radius):
                            return
                    # extra End

                    self.current.points = self.line.points
                    if self.createMode == "rotation":
                        # 保存原始形状类型
                        self.current.shape_type = "rotation"
                    self.finalise()
                elif self.createMode == "linestrip":
                    self.current.addPoint(self.line[1])
                    self.line[0] = self.current[-1]
                    if int(ev.modifiers()) == QtCore.Qt.ControlModifier:
                        self.finalise()
                elif self.createMode in ["ai_polygon", "ai_mask"]:
                    self.current.addPoint(
                        self.line.points[1],
                        label=self.line.point_labels[1],
                    )
                    self.line.points[0] = self.current.points[-1]
                    self.line.point_labels[0] = self.current.point_labels[-1]
                    if ev.modifiers() & QtCore.Qt.ControlModifier:
                        self.finalise()
            elif not self.outOfPixmap(pos):
                # Create new shape.
                self.current = Shape(
                    shape_type="points"
                    if self.createMode in ["ai_polygon", "ai_mask"]
                    else self.createMode
                )
                self.current.addPoint(pos, label=0 if is_shift_pressed else 1)
                if self.createMode == "point":
                    self.finalise()
                elif (
                        self.createMode in ["ai_polygon", "ai_mask"]
                        and ev.modifiers() & QtCore.Qt.ControlModifier
                ):
                    self.finalise()
                else:
                    if self.createMode == "circle":
                        self.current.shape_type = "circle"
                    self.line.points = [pos, pos]
                    if (
                            self.createMode in ["ai_polygon", "ai_mask"]
                            and is_shift_pressed
                    ):
                        self.line.point_labels = [0, 0]
                    else:
                        self.line.point_labels = [1, 1]
                    self.setHiding()
                    self.drawingPolygon.emit(True)
                    self.update()
        elif self.editing():
            if self.selectedEdge():
                self.addPointToEdge()
            elif (
                    self.selectedVertex()
                    and int(ev.modifiers()) == QtCore.Qt.ShiftModifier
            ):
                # Delete point if: left-click + SHIFT on a point
                self.removeSelectedPoint()

            # 单击选择多边形
            group_mode = int(ev.modifiers()) == QtCore.Qt.ControlModifier
            self.selectShapePoint(pos, multiple_selection_mode=group_mode)
            self.prevPoint = pos
            self.repaint()

    def mouse_right_click(self, ev, pos: QtCore.QPointF):
        group_mode = int(ev.modifiers()) == QtCore.Qt.ControlModifier
        if not self.selectedShapes or (
                self.hShape is not None and self.hShape not in self.selectedShapes
        ):
            self.selectShapePoint(pos, multiple_selection_mode=group_mode)
            self.repaint()
        self.prevPoint = pos

    def mousePressEvent(self, ev, need_transform=True):
        # extra 鼠标坐标转换
        if need_transform:
            # 鼠标点击的坐标,转换为图片坐标
            if QT5:
                pos = self.transformPos(ev.localPos())
            else:
                pos = self.transformPos(ev.posF())
        else:
            # 代码传入的坐标,不需要转换
            pos = ev.localPos() if QT5 else ev.posF()
        # extra End

        # extra 右键修改标注
        if (ev.button() == QtCore.Qt.RightButton or 
            (ev.button() == QtCore.Qt.LeftButton and ev.modifiers() & QtCore.Qt.AltModifier)) and self.drawing():
            # 如果启用了画笔功能，右键或Alt+左键进入消除模式
            if self.brush_enabled:
                if not self.outOfPixmap(pos):
                    self.brush_drawing = True
                    self.brush_erase_mode = True  # 标记为消除模式
                    self.brush_points = [pos]  # 重置画笔点集并添加第一个点
                    self.prevPoint = pos
                    self.update()
                    # 设置鼠标样式为十字形
                    self.overrideCursor(CURSOR_DRAW)
                return
                
            if not self.current:
                if not self.outOfPixmap(pos):
                    self.drawing_with_right_btn = True
                    self.current = Shape(
                        shape_type="polygon"
                    )
                    self.drawingPolygon.emit(True)
                    self.current.addPoint(pos, label=1)
            return
        # extra End

        if ev.button() == QtCore.Qt.LeftButton:
            # 如果启用了画笔功能且在绘图模式，开始画笔绘制
            if self.brush_enabled and self.drawing():
                if not self.outOfPixmap(pos):
                    self.brush_drawing = True
                    self.brush_erase_mode = False  # 标记为增加模式（左键）
                    self.brush_points = [pos]  # 重置画笔点集并添加第一个点
                    self.prevPoint = pos
                    self.update()
                    # 设置鼠标样式为十字形
                    self.overrideCursor(CURSOR_DRAW)
                return
                
            # 优先处理旋转框的特殊交互元素（箭头）
            if self.editing():
                # 检查是否启用箭头显示
                if getattr(STORE, 'canvas_display_rotation_arrow', True):
                    # 遍历所有可见的形状，优先检查旋转框的箭头
                    for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
                        if shape.shape_type == "rotation":
                            # 检查是否点击在箭头上
                            if shape.isArrowHit(pos, self.epsilon):
                                self.draggingArrow = True
                                self.hArrowShape = shape
                                self.deSelectShape()
                                self.selectShapes([shape])  # 修改为selectShapes
                                self.update()
                                return
            
            # 只有在编辑模式下，且确实没有选中任何形状和顶点时，才启动画布拖动或多选框
            if (self.editing() and 
                not self.selectedVertex() and 
                not self.selectedShapes and
                not self.hShape and
                not self.current):
                
                # 检查是否按下Shift键
                shift_pressed = int(ev.modifiers()) == QtCore.Qt.ShiftModifier
                
                if shift_pressed:
                    # Shift+拖动：启动多选框功能
                    logger.info("[DEBUG] 启动Shift+拖动多选框功能")
                    self.createMode = "rectangle"
                    self.current = Shape(
                        shape_type="points"
                        if self.createMode in ["ai_polygon", "ai_mask"]
                        else self.createMode
                    )
                    self.current.addPoint(pos, label=0)
                    
                    self.line.points = [pos, pos]
                    self.line.point_labels = [1, 1]
                    self.setHiding()
                    self.update()
                    self.current.highlightClear()
                    return
                else:
                    # 普通拖动：启动画布拖动功能
                    self.draggingCanvas = True
                    self.canvasDragStart = ev.pos() / self.scale
                    # 画布偏移量变量名根据实际情况调整
                    self.canvasOffsetStart = self.offset if hasattr(self, 'offset') else QtCore.QPointF(0, 0)
                    self.overrideCursor(QtCore.Qt.OpenHandCursor)
                    return
                    
            self.mouse_left_click(ev, pos)

        elif ev.button() == QtCore.Qt.RightButton and self.editing():
            self.mouse_right_click(ev, pos)

    def two_points_close_enough(self, p1, p2):
        return labelme.utils.distance(p1 - p2) < (self.two_points_distance / self.scale)

    def boundedMoveVertex(self, pos: QtCore.QPointF):
        index, shape = self.hVertex, self.hShape
        # extra 移动圆半径的点时,圆是否在图片内
        if shape.shape_type == ShapeType.CIRCLE:
            center_point = shape.points[0]
            if index == 1:
                # 圆心和半径, 绘制的圆是否在图片内
                radius = labelme.utils.distance(shape.points[0] - pos)
                if not self.is_circle_in_image(center_point, radius):
                    return
            else:
                # 圆心和半径, 绘制的圆是否在图片内
                radius = labelme.utils.distance(shape.points[1] - pos)
                if not self.is_circle_in_image(pos, radius):
                    return
        # extra End

        # 旋转框的顶点移动需要完全重写，确保始终保持矩形结构
        if shape.shape_type == ShapeType.ROTATION and len(shape.points) == 4:
            # 防止超出画布边界
            if self.outOfPixmap(pos):
                pos = self.intersectionPoint(None, pos)
                
            # 保存当前的旋转角度
            current_rotation = shape.direction
            
            # 找出对角点索引和点
            opposite_index = (index + 2) % 4
            opposite_point = shape.points[opposite_index]
            
            # 找出相邻点索引
            prev_index = (index - 1) % 4
            next_index = (index + 1) % 4
            
            # 矩形的中心点
            center_x = (shape.points[0].x() + shape.points[2].x()) / 2
            center_y = (shape.points[0].y() + shape.points[2].y()) / 2
            center = QtCore.QPointF(center_x, center_y)
            
            # 计算原始矩形的旋转方向向量
            dir_rad = math.radians(current_rotation)
            dir_vector = QtCore.QPointF(math.cos(dir_rad), math.sin(dir_rad))
            
            # 将鼠标位置转换为相对于对角点的向量
            drag_vector = QtCore.QPointF(pos.x() - opposite_point.x(), pos.y() - opposite_point.y())
            
            # 计算拖动向量在旋转方向和垂直方向的投影
            # 旋转方向的投影
            proj_h = drag_vector.x() * dir_vector.x() + drag_vector.y() * dir_vector.y()
            # 垂直方向的投影
            perp_vector = QtCore.QPointF(-dir_vector.y(), dir_vector.x())
            proj_v = drag_vector.x() * perp_vector.x() + drag_vector.y() * perp_vector.y()
            
            # 确保最小尺寸
            min_size = 5.0
            if abs(proj_h) < min_size or abs(proj_v) < min_size:
                return
            
            # 计算新的矩形四个点坐标
            # 计算半宽和半高
            half_width = abs(proj_h) / 2
            half_height = abs(proj_v) / 2
            
            # 使用方向向量和垂直向量，基于对角点计算其他三个点
            h_vector = QtCore.QPointF(dir_vector.x() * half_width * 2, dir_vector.y() * half_width * 2)
            h_vector = h_vector if proj_h > 0 else QtCore.QPointF(-h_vector.x(), -h_vector.y())
            
            v_vector = QtCore.QPointF(perp_vector.x() * half_height * 2, perp_vector.y() * half_height * 2)
            v_vector = v_vector if proj_v > 0 else QtCore.QPointF(-v_vector.x(), -v_vector.y())
            
            # 基于对角点计算其他三个点
            points = [None] * 4
            points[opposite_index] = QtCore.QPointF(opposite_point)  # 对角点不变
            
            # 根据对角点索引，计算其他三个点
            points[index] = QtCore.QPointF(opposite_point.x() + h_vector.x() + v_vector.x(), 
                                          opposite_point.y() + h_vector.y() + v_vector.y())
            
            points[prev_index] = QtCore.QPointF(opposite_point.x() + h_vector.x(), 
                                              opposite_point.y() + h_vector.y())
            
            points[next_index] = QtCore.QPointF(opposite_point.x() + v_vector.x(), 
                                              opposite_point.y() + v_vector.y())
            
            # 应用新的点到形状
            shape.points = points
            
            # 重新计算中心点
            center_x = (shape.points[0].x() + shape.points[2].x()) / 2
            center_y = (shape.points[0].y() + shape.points[2].y()) / 2
            center = QtCore.QPointF(center_x, center_y)
            
            # 更新箭头中心位置
            if hasattr(shape, 'arrow_center'):
                shape.arrow_center = center
                
                # 更新箭头终点位置
                if hasattr(shape, 'arrow_end'):
                    # 计算箭头长度
                    new_width = labelme.utils.distance(shape.points[0] - shape.points[1])
                    new_height = labelme.utils.distance(shape.points[1] - shape.points[2])
                    arrow_length = max(new_width, new_height) * 0.3
                    
                    angle_rad = math.radians(current_rotation)
                    end_x = center.x() + arrow_length * math.cos(angle_rad)
                    end_y = center.y() + arrow_length * math.sin(angle_rad)
                    shape.arrow_end = QtCore.QPointF(end_x, end_y)
            
            # 确保方向保持不变
            shape.direction = current_rotation
                    
            # 更新显示
            self.update()
            self.shapeMoved.emit()
            return
                
        # 原始逻辑（非旋转框的处理）
        point = shape[index]
        if self.outOfPixmap(pos):
            pos = self.intersectionPoint(None, pos)
        shape.moveVertexBy(index, pos - point)

    def intersectionPoint(self, p1, p2):
        """
        p1: the last point of the current shape
        p2: the current mouse position
        """
        return QtCore.QPointF(
            max(0, min(p2.x(), self.pixmap.width() - 0.001)),
            max(0, min(p2.y(), self.pixmap.height() - 0.001)),
        )

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        pos = self.transformPos(ev.pos())

        # 画布拖动处理
        if self.draggingCanvas and QtCore.Qt.LeftButton & ev.buttons():
            # 使用原始鼠标坐标计算增量，避免重复转换
            raw_pos = ev.pos() / self.scale
            delta = raw_pos - self.canvasDragStart
            # 画布偏移量变量名根据实际情况调整
            if hasattr(self, 'offset'):
                self.offset = self.canvasOffsetStart + delta
            self.update()
            return

        # 画笔绘制处理
        if self.brush_enabled and self.brush_drawing and self.drawing():
            # 支持左键和右键画笔模式
            is_drawing = (QtCore.Qt.LeftButton & ev.buttons()) or (QtCore.Qt.RightButton & ev.buttons())
            if is_drawing:
                if self.outOfPixmap(pos):
                    # 不允许在图像外绘制
                    pos = self.intersectionPoint(self.prevPoint if self.prevPoint else pos, pos)
                    
                # 添加点到画笔路径，确保点之间的距离适中（不要太密也不要太稀疏）
                if not self.brush_points:
                    # 如果是第一个点，直接添加
                    self.brush_points.append(pos)
                    self.prevPoint = pos
                else:
                    # 计算与上一个点的距离
                    last_point = self.brush_points[-1]
                    distance = labelme.utils.distance(pos - last_point)
                    
                    # 如果距离超过阈值，添加新点
                    # 这里使用画笔大小的一小部分作为阈值，确保曲线平滑
                    # 考虑缩放因子，使采样点间距随缩放变化
                    min_distance = max(1.0, self.brush_size / 8.0)
                    if distance >= min_distance:
                        self.brush_points.append(pos)
                        self.prevPoint = pos
                
                # 强制更新画布显示
                self.update()
                return

        self.mouseMoved.emit(pos)

        self.prevMovePoint = pos
        self.restoreCursor()

        is_shift_pressed = ev.modifiers() & QtCore.Qt.ShiftModifier

        # 箭头拖拽处理 - 优先级最高
        if self.draggingArrow and self.hArrowShape and QtCore.Qt.LeftButton & ev.buttons():
            shape = self.hArrowShape
            

            center_x = sum(p.x() for p in shape.points) / len(shape.points)
            center_y = sum(p.y() for p in shape.points) / len(shape.points)
            center = QtCore.QPointF(center_x, center_y)


            # 计算鼠标位置相对于中心点的角度
            dx = pos.x() - center.x()
            dy = pos.y() - center.y()

            # 计算新角度（屏幕坐标系y轴向下为正，所以用y而非-y）
            new_angle = math.degrees(math.atan2(dy, dx))

            # print(f"坐标信息: 鼠标位置({pos.x()}, {pos.y()}), 中心点({center.x()}, {center.y()})")
            # print(f"偏移量: dx={dx:.1f}, dy={dy:.1f}")
            # print(f"角度计算: 弧度值={math.atan2(dy, dx):.3f}, 转换角度={new_angle:.1f}°")
            # print(
            #     f"方向变化: 当前方向={shape.direction:.1f}°, 新角度={new_angle:.1f}°, 变化量={new_angle - shape.direction:.1f}°")
            # print(f"归一化角度: {new_angle % 360:.1f}° (0-360°范围内)")
            # print("-" * 50)

            # 将角度调整到0-360度范围
            new_angle = new_angle % 360
            if new_angle < 0:
                new_angle += 360
                
            # 计算角度差（当前角度与新角度的差值）
            old_angle = shape.direction
            angle_diff = new_angle - old_angle
            
            # 设置新角度
            shape.direction = new_angle
            
            # 旋转整个形状的顶点
            self.rotateShape(shape, angle_diff)

            # 更新显示
            self.update()
            self.shapeMoved.emit()
            return
            
        # 如果画笔功能启用，即使不在绘制过程中也更新预览圆
        elif self.brush_enabled and self.drawing():
            self.update()  # 强制更新以显示预览圆
            
        # extra 右键修改标注 | 左键连续标注
        if (self.drawing() and self.drawing_with_right_btn) or (
                self.draw_polygon_with_mousemove and self.createMode == "polygon"):
            if self.current is not None:
                # 间隔一定的距离才能画下一个点
                if len(self.current.points) > 0 and self.two_points_close_enough(pos, self.current[-1]):
                    return
                self.current.addPoint(pos, label=1)
                self.line.points = [self.current[-1], pos]
                self.line.point_labels = [1, 1]
                self.repaint()
                return
        # extra End

        # Polygon drawing.
        if self.drawing():
            if self.createMode in ["ai_polygon", "ai_mask"]:
                self.line.shape_type = "points"
            elif self.createMode == "rotation":
                # 旋转框绘制过程临时显示为矩形
                self.line.shape_type = "rectangle"
            else:
                self.line.shape_type = self.createMode

            self.overrideCursor(CURSOR_DRAW)
            if not self.current:
                self.repaint()  # draw crosshair
                return

            if self.outOfPixmap(pos):
                # Don't allow the user to draw outside the pixmap.
                # Project the point to the pixmap's edges.
                pos = self.intersectionPoint(self.current[-1], pos)
            elif (
                    self.snapping
                    and len(self.current) > 1
                    and self.createMode == "polygon"
                    and self.closeEnough(pos, self.current[0])
            ):
                # Attract line to starting point and
                # colorise to alert the user.
                pos = self.current[0]
                self.overrideCursor(CURSOR_POINT)
                self.current.highlightVertex(0, Shape.NEAR_VERTEX)
            if self.createMode in ["polygon", "linestrip"]:
                self.line.points = [self.current[-1], pos]
                self.line.point_labels = [1, 1]
            elif self.createMode in ["ai_polygon", "ai_mask"]:
                self.line.points = [self.current.points[-1], pos]
                self.line.point_labels = [
                    self.current.point_labels[-1],
                    0 if is_shift_pressed else 1,
                ]
            elif self.createMode in ["rectangle", "rotation"]:
                # 旋转框和矩形一样，临时显示为矩形
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "circle":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.shape_type = "circle"
            elif self.createMode == "line":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "point":
                self.line.points = [self.current[0]]
                self.line.point_labels = [1]
                self.line.close()
            assert len(self.line.points) == len(self.line.point_labels)
            self.repaint()
            self.current.highlightClear()
            return

        # Polygon copy moving.
        if QtCore.Qt.RightButton & ev.buttons():
            if self.selectedShapesCopy and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapesCopy, pos)
                self.repaint()
            elif self.selectedShapes:
                self.selectedShapesCopy = [s.copy() for s in self.selectedShapes]
                self.repaint()
            return

        # Polygon/Vertex moving.
        if QtCore.Qt.LeftButton & ev.buttons():
            # extra Edit时,左键多选框移动
            if self.current:
                self.line.shape_type = self.createMode

                if self.outOfPixmap(pos):
                    # Don't allow the user to draw outside the pixmap.
                    # Project the point to the pixmap's edges.
                    pos = self.intersectionPoint(self.current[-1], pos)

                if self.createMode == "rectangle":
                    self.line.points = [self.current[0], pos]
                    self.line.point_labels = [1, 1]
                    self.line.close()

                # 多选选中状态
                x1 = self.line.points[0].x()
                y1 = self.line.points[0].y()
                x2 = self.line.points[1].x()
                y2 = self.line.points[1].y()
                xMax = max([x1, x2])
                yMax = max([y1, y2])
                xMin = min([x1, x2])
                yMin = min([y1, y2])

                # 取消选中,并重新选中在当前框内的多边形
                self.deSelectShape()

                selected_shapes = []
                for shape in self.shapes:
                    if shape is None: continue
                    for pnt in shape.points:
                        if xMax >= pnt.x() >= xMin and yMax >= pnt.y() >= yMin:
                            selected_shapes.append(shape)
                            break
                self.selectShapes(selected_shapes)

                self.repaint()
                self.current.highlightClear()
                return
            # extra End

            # moving vertex
            if self.selectedVertex():
                self.boundedMoveVertex(pos)
                self.repaint()
                self.movingShape = True
            # moving selected shapes
            elif self.selectedShapes and self.prevPoint:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapes, pos)
                self.repaint()
                self.movingShape = True
            return

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        self.setToolTip(self.tr("Image"))
        for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
            # Look for a nearby vertex to highlight. If that fails,
            # check if we happen to be inside a shape.
            index = shape.nearestVertex(pos, self.epsilon)
            index_edge = shape.nearestEdge(pos, self.epsilon)
            if index is not None:
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.prevhVertex = self.hVertex = index
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge
                self.hEdge = None
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip(self.tr("Click & drag to move point"))
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif index_edge is not None and shape.canAddPoint():
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.prevhVertex = self.hVertex
                self.hVertex = None
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge = index_edge
                self.overrideCursor(CURSOR_POINT)
                self.setToolTip(self.tr("Click to create point"))
                self.setStatusTip(self.toolTip())
                self.update()
                break
            elif shape.containsPoint(pos):
                if self.selectedVertex():
                    self.hShape.highlightClear()
                self.prevhVertex = self.hVertex
                self.hVertex = None
                self.prevhShape = self.hShape = shape
                self.prevhEdge = self.hEdge
                self.hEdge = None
                self.setToolTip(
                    self.tr("Click & drag to move shape '%s'") % shape.label
                )
                self.setStatusTip(self.toolTip())
                self.overrideCursor(CURSOR_GRAB)
                self.update()
                break
        else:  # Nothing found, clear highlights, reset state.
            self.unHighlight()
        self.vertexSelected.emit(self.hVertex is not None)

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton and self.editing():
            menu = self.menus[len(self.selectedShapesCopy) > 0]
            self.restoreCursor()
            if not menu.exec_(self.mapToGlobal(ev.pos())) and self.selectedShapesCopy:
                # Cancel the move by deleting the shadow copy.
                self.selectedShapesCopy = []
                self.repaint()
        elif ev.button() == QtCore.Qt.LeftButton or (ev.button() == QtCore.Qt.RightButton and self.brush_enabled):
            # 如果是画笔绘制结束
            if self.brush_drawing and self.brush_enabled and self.brush_points:
                self.brush_drawing = False
                is_erase_mode = self.brush_erase_mode
                self.brush_erase_mode = False
                
                if len(self.brush_points) >= 1:
                    try:
                        # 使用numpy和OpenCV生成更精确的边缘轮廓
                        import cv2
                        import numpy as np
                        from shapely.geometry import Polygon as ShapelyPolygon
                        from shapely.geometry import Point as ShapelyPoint
                        from shapely.geometry import LineString as ShapelyLineString
                        
                        # 获取图像尺寸
                        img_width = self.pixmap.width()
                        img_height = self.pixmap.height()

                        # 确定画笔路径的包围矩形，并扩大一定边距
                        x_coords = [p.x() for p in self.brush_points]
                        y_coords = [p.y() for p in self.brush_points]
                        min_x = max(0, min(x_coords) - self.brush_size * 2)
                        max_x = min(img_width, max(x_coords) + self.brush_size * 2)
                        min_y = max(0, min(y_coords) - self.brush_size * 2)
                        max_y = min(img_height, max(y_coords) + self.brush_size * 2)
                        
                        # 创建大小合适的mask
                        width = int(max_x - min_x) + 1
                        height = int(max_y - min_y) + 1
                        
                        if width <= 0 or height <= 0:
                            # 无效尺寸，取消操作
                            self.brush_points = []
                            self.update()
                            return
                            
                        # 创建空白掩码
                        mask = np.zeros((height, width), dtype=np.uint8)
                        
                        # 将画笔路径点转换为相对于mask的坐标
                        points = []
                        for p in self.brush_points:
                            x = int(p.x() - min_x)
                            y = int(p.y() - min_y)
                            points.append([x, y])
                        points = np.array(points, dtype=np.int32)
                        
                        if len(self.brush_points) == 1:
                            # 如果只有一个点，绘制一个圆形
                            center_x = int(self.brush_points[0].x() - min_x)
                            center_y = int(self.brush_points[0].y() - min_y)
                            cv2.circle(mask, (center_x, center_y), int(self.brush_size), 255, -1)
                        else:
                            # 多点时绘制路径
                            cv2.polylines(mask, [points], False, 255, int(self.brush_size * 2))
                        
                        # 检查是否需要闭合形状
                        is_closed_shape = False
                        if len(self.brush_points) > 3:
                            first_px = int(self.brush_points[0].x() - min_x)
                            first_py = int(self.brush_points[0].y() - min_y)
                            last_px = int(self.brush_points[-1].x() - min_x)
                            last_py = int(self.brush_points[-1].y() - min_y)
                            
                            # 计算首尾距离
                            distance = np.sqrt((last_px - first_px)**2 + (last_py - first_py)**2)
                            # 如果距离小于画笔大小的两倍，判定为需要闭合的环形
                            if distance < self.brush_size * 2:
                                is_closed_shape = True
                                # 连接首尾
                                cv2.line(mask, (first_px, first_py), (last_px, last_py), 255, int(self.brush_size * 2))
                        
                        # 检查是否设置了填充闭合区域选项
                        should_fill = STORE.canvas_brush_fill_region
                        
                        # 根据是否需要填充选择不同的轮廓检测方法
                        if should_fill:
                            # 如果需要填充闭合区域，使用RETR_EXTERNAL找最外层轮廓
                            contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        else:
                            # 如果不需要填充，使用RETR_TREE找所有轮廓
                            contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                        
                        if contours:
                            # 按面积排序，取最大的轮廓
                            contours = sorted(contours, key=cv2.contourArea, reverse=True)
                            contour = contours[0]
                            
                            # 简化轮廓点
                            epsilon = 0.002 * cv2.arcLength(contour, True)
                            approx = cv2.approxPolyDP(contour, epsilon, True)
                            
                            # 创建多边形点列表
                            brush_points = []
                            for p in approx:
                                x = p[0][0] + min_x
                                y = p[0][1] + min_y
                                # 确保点在图像范围内
                                x = max(0, min(x, img_width - 1))
                                y = max(0, min(y, img_height - 1))
                                brush_points.append(QtCore.QPointF(x, y))
                            
                            # 如果不填充且轮廓形成了环状（首尾距离很近），则断开环
                            if not should_fill and len(brush_points) > 3:
                                # 检查是否形成环状（首尾点距离很近）
                                first_point = brush_points[0]
                                last_point = brush_points[-1]
                                if (first_point.x() - last_point.x())**2 + (first_point.y() - last_point.y())**2 < (self.brush_size*2)**2:
                                    # 找到一个合适的位置断开环状
                                    # 计算轮廓的中心点
                                    center_x = sum(p.x() for p in brush_points) / len(brush_points)
                                    center_y = sum(p.y() for p in brush_points) / len(brush_points)
                                    
                                    # 找到距离中心最远的点，作为断开点
                                    max_dist = -1
                                    break_idx = 0
                                    for i, p in enumerate(brush_points):
                                        dist = (p.x() - center_x)**2 + (p.y() - center_y)**2
                                        if dist > max_dist:
                                            max_dist = dist
                                            break_idx = i
                                    
                                    # 重新排列点序列，使断开点在首尾
                                    new_points = []
                                    # 从断开点到末尾
                                    for i in range(break_idx, len(brush_points)):
                                        new_points.append(brush_points[i])
                                    # 从开始到断开点前一个点
                                    for i in range(0, break_idx):
                                        new_points.append(brush_points[i])
                                    
                                    # 用新点序列替换原点序列
                                    brush_points = new_points
                            
                            if len(brush_points) >= 1:
                                # 首先尝试找到与画笔路径相交的第一个多边形
                                # 创建画笔轮廓的Shapely对象
                                brush_polygon = ShapelyPolygon([(p.x(), p.y()) for p in brush_points])
                                
                                # 查找是否与现有多边形相交
                                target_shape = None
                                visible_dict = self.visible
                                
                                # 只有当STORE.canvas_brush_modify_shapes为True时才查找现有形状
                                modify_existing = getattr(STORE, 'canvas_brush_modify_shapes', True)
                                
                                if modify_existing:
                                    # 从上到下遍历形状（可见的形状）
                                    for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
                                        # 跳过非多边形形状
                                        if shape.shape_type not in ['polygon', 'rectangle']:
                                            continue
                                            
                                        # 将矩形转换为多边形进行处理
                                        if shape.shape_type == 'rectangle':
                                            temp_shape = shape.copy()
                                            temp_shape.convert_to_polygon()
                                            shape_points = temp_shape.points
                                        else:
                                            shape_points = shape.points
                                            
                                        # 创建Shapely多边形对象
                                        try:
                                            shape_polygon = ShapelyPolygon([(p.x(), p.y()) for p in shape_points])
                                            
                                            # 检查是否与画笔多边形相交
                                            if shape_polygon.intersects(brush_polygon):
                                                target_shape = shape
                                                break
                                        except Exception as e:
                                            logger.error(f"Error processing shape: {str(e)}")
                                            continue
                                
                                # 如果找到了目标形状，则修改它而不是创建新形状
                                if target_shape and modify_existing:
                                    # 如果是矩形，先转换为多边形
                                    if target_shape.shape_type == 'rectangle':
                                        target_shape.convert_to_polygon()
                                    
                                    # 创建目标形状的Shapely对象
                                    target_polygon = ShapelyPolygon([(p.x(), p.y()) for p in target_shape.points])
                                    
                                    # 根据是否为消除模式选择操作
                                    if is_erase_mode:
                                        # 消除模式：减去画笔区域
                                        result = target_polygon.difference(brush_polygon)
                                    else:
                                        # 增加模式：合并画笔区域
                                        result = target_polygon.union(brush_polygon)
                                    
                                    # 处理结果
                                    if result.is_empty:
                                        # 如果结果为空（消除了全部区域），则删除形状
                                        self.shapes.remove(target_shape)
                                    else:
                                        # 根据结果类型更新形状点
                                        if result.geom_type == 'Polygon':
                                            # 单个多边形结果
                                            exterior_coords = list(result.exterior.coords)
                                            new_points = [QtCore.QPointF(x, y) for x, y in exterior_coords]
                                            target_shape.points = new_points
                                        elif result.geom_type == 'MultiPolygon':
                                            # 多个多边形结果，选择面积最大的
                                            largest_polygon = max(result.geoms, key=lambda p: p.area)
                                            exterior_coords = list(largest_polygon.exterior.coords)
                                            new_points = [QtCore.QPointF(x, y) for x, y in exterior_coords]
                                            target_shape.points = new_points
                                        
                                    # 更新形状显示
                                    self.update()
                                    self.storeShapes()
                                    self.shapeMoved.emit()
                                else:
                                    # 没有找到目标形状或禁用了形状修改功能，创建一个新的形状（仅适用于增加模式）
                                    if not is_erase_mode:
                                        # 尝试获取标签
                                        label = ""
                                        
                                        # 1. 从当前形状获取标签（如果有）
                                        if self.current and self.current.label:
                                            label = self.current.label
                                        # 2. 如果没有当前形状或当前形状没有标签，从选中的形状获取标签
                                        elif self.selectedShapes and len(self.selectedShapes) > 0:
                                            label = self.selectedShapes[0].label
                                        # 3. 如果仍然没有标签，尝试从最后一个形状获取标签
                                        elif self.shapes and len(self.shapes) > 0:
                                            label = self.shapes[-1].label
                                        
                                        # 创建形状对象
                                        shape = Shape(
                                            label=label,
                                            shape_type="polygon",
                                            flags={},
                                            group_id=None,
                                            description="",
                                        )
                                        
                                        # 添加点
                                        for p in brush_points:
                                            shape.addPoint(p)
                                        
                                        # 保存当前形状并调用finalise方法
                                        # 这会触发newShape信号并添加到shapes列表
                                        self.current = shape
                                        self.finalise()
                        
                        # 清理画笔状态
                        self.brush_points = []
                        self.update()
                        
                    except Exception as e:
                        logger.error(f"Error creating shape from brush: {str(e)}")
                        self.brush_points = []
                        self.update()
                        return

            # 如果是箭头拖拽结束
            if self.draggingArrow:
                self.draggingArrow = False
                self.hArrowShape = None
                self.storeShapes()
                self.repaint()
                return
                
            if self.editing():
                if (
                        self.hShape is not None
                        and self.hShapeIsSelected
                        and not self.movingShape
                ):
                    self.selectionChanged.emit(
                        [x for x in self.selectedShapes if x != self.hShape]
                    )

                # extra Edit时,左键多选框结束
                else:
                    self.current = None  # clear current shape
                    self.setEditing(True)
                # extra End

        # extra 右键修改标注结束
        elif ev.button() == QtCore.Qt.RightButton and self.drawing() and not self.brush_enabled:
            self.drawing_with_right_btn = False
            self.right_btn_modify_shape()
            self.clear_current_shape()
            self.shapeMoved.emit()
            return
        # extra End

        if self.movingShape and self.hShape:
            index = self.shapes.index(self.hShape)
            if self.shapesBackups[-1][index].points != self.shapes[index].points:
                self.storeShapes()
                self.shapeMoved.emit()

            self.movingShape = False

        # 画布拖动释放
        if self.draggingCanvas:
            self.draggingCanvas = False
            self.restoreCursor()
            return

    def wheelEvent(self, ev):
        # 优化：注释掉Ctrl依赖，滚轮直接缩放
        if not hasattr(self, 'pixmap') or self.pixmap is None or self.pixmap.isNull():
            return
        if QT5:
            # mods = ev.modifiers()
            delta = ev.angleDelta()
            # if QtCore.Qt.ControlModifier == int(mods):
            #     # with Ctrl/Command key
            #     # zoom
            #     self.zoomRequest.emit(delta.y(), ev.pos())
            #     # extra shift+滚轮横向滚动
            #     # https://github.com/wkentaro/labelme/pull/1472
            #     elif QtCore.Qt.ShiftModifier == int(mods):
            #         # side scroll
            #         self.scrollRequest.emit(delta.y(), QtCore.Qt.Horizontal)
            #         self.scrollRequest.emit(delta.x(), QtCore.Qt.Vertical)
            #     else:
            #         # scroll
            #         self.scrollRequest.emit(delta.x(), QtCore.Qt.Horizontal)
            #         self.scrollRequest.emit(delta.y(), QtCore.Qt.Vertical)
            # 现在无论是否按Ctrl，滚轮都缩放
            self.zoomRequest.emit(delta.y(), ev.pos())
            # 注释掉所有滚动条相关代码，避免缩放时触发滚动条
            # mods = ev.modifiers()
            # if QtCore.Qt.ShiftModifier == int(mods):
            #     self.scrollRequest.emit(delta.y(), QtCore.Qt.Horizontal)
            #     self.scrollRequest.emit(delta.x(), QtCore.Qt.Vertical)
            # else:
            #     self.scrollRequest.emit(delta.x(), QtCore.Qt.Horizontal)
            #     self.scrollRequest.emit(delta.y(), QtCore.Qt.Vertical)
        else:
            if ev.orientation() == QtCore.Qt.Vertical:
                # mods = ev.modifiers()
                # if QtCore.Qt.ControlModifier == int(mods):
                #     # with Ctrl/Command key
                #     self.zoomRequest.emit(ev.delta(), ev.pos())
                # else:
                #     self.scrollRequest.emit(
                #         ev.delta(),
                #         QtCore.Qt.Horizontal
                #         if (QtCore.Qt.ShiftModifier == int(mods))
                #         else QtCore.Qt.Vertical,
                #     )
                self.zoomRequest.emit(ev.delta(), ev.pos())
            # else:
            #     self.scrollRequest.emit(ev.delta(), QtCore.Qt.Horizontal)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        # extra 双击 shape 编辑其名称
        if ev.button() == QtCore.Qt.LeftButton and self.editing() and len(self.selectedShapes or []) == 1:
            STORE.edit_label_name()
            self.selectShapes([])  # 防止点击后不修改名称,再次点击时不会触发
            return
        # extra End

        if self.double_click != "close":
            return

        if (
                self.createMode == "polygon" and self.canCloseShape()
        ) or self.createMode in ["ai_polygon", "ai_mask"]:
            # extra ai_polygon 时, 双击结束多边形绘制, 防止点击了 canvas 之外的地方
            if self.current:
                self.finalise()
            # extra End

    # endregion

    def loadPixmap(self, pixmap:QtGui.QPixmap, clear_shapes=True):
        self.pixmap = pixmap
        if self._ai_model and self.createMode in ["ai_polygon", "ai_mask"]:
            if not pixmap.isNull(): # extra 当 pixmap 为空时，不需要调用 _ai_model
                self._ai_model.set_image(
                    image=labelme.utils.img_qt_to_arr(self.pixmap.toImage())
                )
        if clear_shapes:
            self.shapes = []
        self.update()

    def paintEvent(self, event):
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = self._painter
        p.begin(self)

        # 不启用抗锯齿，保持原始像素
        # p.setRenderHint(QtGui.QPainter.Antialiasing)
        # p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)
        # 叠加画布偏移量
        p.translate(self.offsetToCenter() + self.offset)

        p.drawPixmap(0, 0, self.pixmap)
        
        # 将坐标系统改回正常比例以便绘制UI元素
        p.scale(1 / self.scale, 1 / self.scale)

        # draw crosshair
        if (
                self.drawing()
                and self.createMode in self._crosshair
                and self._crosshair[self.createMode]
                and self.prevMovePoint
                and not self.outOfPixmap(self.prevMovePoint)
        ):
            p.setPen(QtGui.QColor(0, 0, 0))
            p.drawLine(
                0,
                int(self.prevMovePoint.y() * self.scale),
                self.width() - 1,
                int(self.prevMovePoint.y() * self.scale),
            )
            p.drawLine(
                int(self.prevMovePoint.x() * self.scale),
                0,
                int(self.prevMovePoint.x() * self.scale),
                self.height() - 1,
            )
            
        # 绘制画笔预览圆
        if self.brush_enabled and self.drawing() and self.prevMovePoint and not self.outOfPixmap(self.prevMovePoint):
            # 绘制半透明的圆形指示画笔大小
            p.setRenderHint(QtGui.QPainter.Antialiasing)  # 启用抗锯齿
            
            # 设置颜色 - 左键（增加）显示红色，右键（消除）显示蓝色
            brush_color = QtGui.QColor(255, 0, 0, 200) if not self.brush_erase_mode else QtGui.QColor(0, 0, 255, 200)
            
            # 外圈边框
            p.setPen(QtGui.QPen(brush_color, 2.0))
            # 内部填充
            fill_color = QtGui.QColor(brush_color.red(), brush_color.green(), brush_color.blue(), 50)
            p.setBrush(QtGui.QBrush(fill_color))
            
            # 计算圆的半径 - 考虑缩放因子
            radius = self.brush_size * self.scale
            
            # 绘制圆 - 确保位置准确
            center_x = int(self.prevMovePoint.x() * self.scale)
            center_y = int(self.prevMovePoint.y() * self.scale)
            p.drawEllipse(QtCore.QPointF(center_x, center_y), radius, radius)
            
            # 绘制当前画笔轨迹
            if self.brush_drawing and len(self.brush_points) > 1:
                # 设置笔刷样式绘制轨迹
                p.setPen(QtGui.QPen(
                    brush_color, 
                    radius * 2,  # 使用画笔直径作为线宽
                    QtCore.Qt.SolidLine, 
                    QtCore.Qt.RoundCap, 
                    QtCore.Qt.RoundJoin
                ))
                
                # 创建路径
                path = QtGui.QPainterPath()
                
                # 确保所有点都经过正确的坐标变换
                start_point = QtCore.QPointF(
                    int(self.brush_points[0].x() * self.scale),
                    int(self.brush_points[0].y() * self.scale)
                )
                path.moveTo(start_point)
                
                for i in range(1, len(self.brush_points)):
                    next_point = QtCore.QPointF(
                        int(self.brush_points[i].x() * self.scale),
                        int(self.brush_points[i].y() * self.scale)
                    )
                    path.lineTo(next_point)
                
                # 绘制路径
                p.drawPath(path)

        Shape.scale = self.scale
        for shape in self.shapes:
            if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.hShape
                shape.paint(p)
        if self.current:
            self.current.paint(p)
            self.line.paint(p)
        if self.selectedShapesCopy:
            for s in self.selectedShapesCopy:
                s.paint(p)

        if (
                self.fillDrawing()
                and self.createMode == "polygon"
                and self.current is not None
                and len(self.current.points) >= 2
                and self.line.points and len(self.line.points) >= 2  # 确保line至少有两个点
        ):
            drawing_shape = self.current.copy()
            if drawing_shape.fill_color.getRgb()[3] == 0:
                logger.warning(
                    "fill_drawing=true, but fill_color is transparent,"
                    " so forcing to be opaque."
                )
                drawing_shape.fill_color.setAlpha(64)
            drawing_shape.addPoint(self.line[1])
            drawing_shape.fill = True
            drawing_shape.paint(p)
        # extra not self.drawing_with_right_btn 右键修改标注时,绘制多边形
        elif self.createMode == "ai_polygon" and self.current is not None and not self.drawing_with_right_btn and self.line.points and len(self.line.points) >= 2:
            drawing_shape = self.current.copy()
            drawing_shape.addPoint(
                point=self.line.points[1],
                label=self.line.point_labels[1],
            )
            points = self._ai_model.predict_polygon_from_points(
                points=[[point.x(), point.y()] for point in drawing_shape.points],
                point_labels=drawing_shape.point_labels,
            )
            if len(points) > 2:
                drawing_shape.setShapeRefined(
                    shape_type="polygon",
                    points=[QtCore.QPointF(point[0], point[1]) for point in points],
                    point_labels=[1] * len(points),
                )
                drawing_shape.fill = self.fillDrawing()
                drawing_shape.selected = True
                drawing_shape.paint(p)
        elif self.createMode == "ai_mask" and self.current is not None and self.line.points and len(self.line.points) >= 2:
            drawing_shape = self.current.copy()
            drawing_shape.addPoint(
                point=self.line.points[1],
                label=self.line.point_labels[1],
            )
            mask = self._ai_model.predict_mask_from_points(
                points=[[point.x(), point.y()] for point in drawing_shape.points],
                point_labels=drawing_shape.point_labels,
            )
            y1, x1, y2, x2 = imgviz.instances.masks_to_bboxes([mask])[0].astype(int)
            drawing_shape.setShapeRefined(
                shape_type="mask",
                points=[QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2)],
                point_labels=[1, 1],
                mask=mask[y1: y2 + 1, x1: x2 + 1],
            )
            drawing_shape.selected = True
            drawing_shape.paint(p)

        p.end()
        
    # 添加清理画笔绘制内容的方法
    def cancelBrushDrawing(self):
        """取消画笔绘制和其他标注操作，清理所有绘制状态"""
        # 清除画笔状态
        self.brush_drawing = False
        self.brush_erase_mode = False
        self.brush_points = []
        
        # 完全清除当前形状和线条
        self.current = None
        self.line.points = []
        self.line.point_labels = []
        
        # 清除绘制多边形的状态
        self.drawing_with_right_btn = False
        self.drawingPolygon.emit(False)
        
        # 强制重新绘制
        self.update()

    def resetState(self):
        self.restoreCursor()

        # extra self.pixmap = None 会导致鼠标点击事件崩溃
        self.pixmap = QtGui.QPixmap()

        # extra
        # self.movingShape = False  # 修复 ctrl + v 粘贴图片, 同时快速 上下切图,
        self.selectedShapes = []  # 程序崩溃, 因为 self.movingShape, selectedShapes 未重置
        # extra End

        self.shapesBackups = []
        self.update()

    def keyPressEvent(self, ev):
        super().keyPressEvent(ev)
        modifiers = ev.modifiers()
        key = ev.key()

        # 修复ESC键取消标注时残留问题
        if self.drawing() and key == QtCore.Qt.Key_Escape:
            self.cancelBrushDrawing()  # 添加这一行来清理画笔绘制状态

        # 画笔大小调整（使用+和-键替代上下箭头键）
        if self.brush_enabled and self.drawing():
            if key == QtCore.Qt.Key_Plus or key == QtCore.Qt.Key_Equal:  # + 键增大画笔
                # 按1.1倍比例调整画笔大小
                old_size = self.brush_size
                # 先乘以1.1，再取整，确保至少增加1个单位
                new_size = int(self.brush_size * 1.1)
                # 如果取整后没有变化，则至少增加1个单位
                if new_size <= old_size:
                    new_size = old_size + 1
                self.brush_size = new_size  # 不限制最大大小
                
                # 显示提示
                if old_size != self.brush_size:
                    print(f"画笔大小: {self.brush_size}")
                    
                # 更新存储并刷新显示
                STORE.set_canvas_brush_size(self.brush_size)
                self.update()
                return
            elif key == QtCore.Qt.Key_Minus or key == QtCore.Qt.Key_Underscore:  # - 键减小画笔
                # 按1.1倍比例缩小画笔大小
                old_size = self.brush_size
                # 除以1.1后取整
                new_size = int(self.brush_size / 1.1)
                # 如果取整后没有变化，则至少减少1个单位
                if new_size >= old_size:
                    new_size = old_size - 1
                self.brush_size = max(self.min_brush_size, new_size)  # 确保不小于最小大小
                
                # 显示提示
                if old_size != self.brush_size:
                    print(f"画笔大小: {self.brush_size}")
                    
                # 更新存储并刷新显示
                STORE.set_canvas_brush_size(self.brush_size)
                self.update()
                return

        
        
                
    def rotateShape(self, shape, angle):
        """根据给定的角度旋转形状"""
        if not shape or shape.shape_type != "rotation":
            return
            
        # 确保旋转框有足够的点
        if len(shape.points) < 4:
            # 如果点数不够，尝试修复
            if len(shape.points) >= 2:
                # 如果至少有两个点，构建矩形
                x_values = [p.x() for p in shape.points]
                y_values = [p.y() for p in shape.points]
                
                # 计算边界框
                x_min, x_max = min(x_values), max(x_values)
                y_min, y_max = min(y_values), max(y_values)
                
                # 创建四个角点
                shape.points = [
                    QtCore.QPointF(x_min, y_min),  # 左上
                    QtCore.QPointF(x_max, y_min),  # 右上
                    QtCore.QPointF(x_max, y_max),  # 右下
                    QtCore.QPointF(x_min, y_max),  # 左下
                ]
                shape.point_labels = [1, 1, 1, 1]
            else:
                # 如果点不够且无法修复，则放弃旋转
                return

        # 计算中心点
        center_x = sum(p.x() for p in shape.points) / len(shape.points)
        center_y = sum(p.y() for p in shape.points) / len(shape.points)
        center = QtCore.QPointF(center_x, center_y)
        
        # 计算角度差（使用传入的增量角度）
        angle_diff = angle
        
        # 旋转所有点
        for i, point in enumerate(shape.points):
            # 计算相对于中心点的坐标
            dx = point.x() - center.x()
            dy = point.y() - center.y()
            
            # 旋转角度（转为弧度）
            rad = math.radians(angle_diff)
            
            # 应用旋转变换
            new_dx = dx * math.cos(rad) - dy * math.sin(rad)
            new_dy = dx * math.sin(rad) + dy * math.cos(rad)
            
            # 计算新的绝对坐标
            new_x = center.x() + new_dx
            new_y = center.y() + new_dy
            
            # 更新点位置
            shape.points[i] = QtCore.QPointF(new_x, new_y)
        
        # 更新显示
        self.update()
        self.storeShapes()

    """额外函数"""

    def is_circle_in_image(self, circle_center: QtCore.QPointF, radius: float):
        x, y = circle_center.x(), circle_center.y()
        width, height = self.pixmap.width(), self.pixmap.height()

        if (x - radius >= 0 and
                x + radius <= width and
                y - radius >= 0 and
                y + radius <= height):
            return True
        return False

    def clear_current_shape(self):
        self.current = None
        self.line.points = []
        self.line.point_labels = []
        self.drawing_with_right_btn = False
        self.drawingPolygon.emit(False)

    def right_btn_modify_shape(self):
        if self.current:
            if len(self.current) <= 2:
                return
            visible_dict = self.visible

            line_geo = LineString(self.current.get_points_pos())

            # 遍历所有标注是否与 右键绘制的线段 相交
            for shape in self.shapes:
                # 隐藏标注不参与操作
                if not visible_dict[shape]:
                    continue

                if shape.shape_type in ['point', 'line', 'linestrip']:
                    continue

                if shape.shape_type in ['circle']:
                    raidus = labelme.utils.distance(shape.points[0] - shape.points[1])
                    center_point = Point(shape.points[0].x(), shape.points[0].y())
                    shape_geo = center_point.buffer(raidus)

                elif shape.shape_type in ['rectangle']:
                    shape.convert_to_polygon()
                    shape_geo = Polygon([(point.x(), point.y()) for point in shape.points])

                else:
                    shape_geo = Polygon([(point.x(), point.y()) for point in shape.points])

                if not shape_geo.is_valid:
                    # 判断 shape 是否相交,不相交则修正
                    shape_points = shape.get_points_pos()
                    line_points = self.current.get_points_pos()
                    if polygon_intersects_curve(shape_points, line_points):
                        STORE.main_window.fix_shape(shape)
                        return
                    else:
                        continue

                intersection = shape_geo.intersection(line_geo)

                # 判断多边形是否与线段相交
                if not intersection.is_empty:
                    if shape.shape_type in ['circle']:
                        shape.convert_to_polygon()
                        shape_geo = Polygon([(point.x(), point.y()) for point in shape.points])

                    line_polygon = Polygon(line_geo)
                    if not line_polygon.is_valid:
                        return

                        # 端点在内,加上线段外部
                    if shape_geo.contains(Point(line_geo.coords[0])) and shape_geo.contains(Point(line_geo.coords[-1])):
                        new_shape = shape_geo.union(line_polygon)
                        shape.points = [QtCore.QPointF(point[0], point[1]) for point in new_shape.exterior.coords]

                    # 端点在外,减去相交部分
                    elif not shape_geo.contains(Point(line_geo.coords[0])) and not shape_geo.contains(
                            Point(line_geo.coords[-1])):
                        new_shape = shape_geo.difference(line_polygon)
                        if isinstance(new_shape, MultiPolygon):
                            # 取面积最大的
                            new_shape = max([polygon for polygon in new_shape.geoms], key=lambda x: x.area)
                        shape.points = [QtCore.QPointF(point[0], point[1]) for point in new_shape.exterior.coords]
        self.update()

    def boundedShiftShapes(self, shapes):
        # Try to move in one direction, and if it fails in another.
        # Give up if both fail.
        point = shapes[0][0]
        offset = QtCore.QPointF(2.0, 2.0)
        self.offsets = QtCore.QPoint(), QtCore.QPoint()
        self.prevPoint = point
        if not self.boundedMoveShapes(shapes, point - offset):
            self.boundedMoveShapes(shapes, point + offset)

    # 覆盖父类的boundedMoveShapes方法，添加对旋转框的特殊处理
    def boundedMoveShapes(self, shapes, pos):
        """移动形状，确保它们不会移出图像边界，并且保持旋转框的旋转属性"""
        if self.outOfPixmap(pos):
            return False  # No need to move
            
        o1 = pos + self.offsets[0]
        if self.outOfPixmap(o1):
            pos -= QtCore.QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.outOfPixmap(o2):
            pos += QtCore.QPointF(
                min(0, self.pixmap.width() - o2.x()),
                min(0, self.pixmap.height() - o2.y()),
            )
            
        # 计算移动偏移量
        dp = pos - self.prevPoint
        if dp:
            for shape in shapes:
                # 对于旋转框，需要特殊处理
                if shape.shape_type == "rotation":
                    # 保存旋转角度
                    current_rotation = shape.direction
                    
                    # 先按照常规方式移动所有点
                    shape.moveBy(dp)
                    
                    # 计算新的中心点
                    center_x = (shape.points[0].x() + shape.points[2].x()) / 2
                    center_y = (shape.points[0].y() + shape.points[2].y()) / 2
                    center = QtCore.QPointF(center_x, center_y)
                    
                    # 计算旋转方向向量
                    angle_rad = math.radians(current_rotation)
                    dir_vector = QtCore.QPointF(math.cos(angle_rad), math.sin(angle_rad))
                    
                    # 计算与箭头方向平行的边的长度
                    # 计算各个边的方向向量
                    edge_vectors = []
                    for i in range(4):
                        next_i = (i + 1) % 4
                        edge_vec = QtCore.QPointF(
                            shape.points[next_i].x() - shape.points[i].x(),
                            shape.points[next_i].y() - shape.points[i].y()
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
                    
                    # 更新箭头位置
                    shape.arrow_center = arrow_start
                    shape.arrow_end = QtCore.QPointF(end_x, end_y)
                    
                    # 确保方向保持不变
                    shape.direction = current_rotation
                else:
                    # 其他形状的常规移动
                    shape.moveBy(dp)
                    
            self.prevPoint = pos
            return True
        return False

    def finalise(self):
        """结束当前图形的绘制并提交图形"""
        # 如果是旋转框，需要特殊处理..
        if self.current and self.current.shape_type == "rotation":
            # 确保当前形状有足够的点来创建旋转框
            if len(self.current.points) >= 2:
                # 从当前的矩形创建旋转框，保存原始图形的位置信息
                x1, y1 = self.current.points[0].x(), self.current.points[0].y()
                x2, y2 = self.current.points[1].x(), self.current.points[1].y()

                # 确保矩形的四个角点
                points = [
                    QtCore.QPointF(x1, y1),  # 左上
                    QtCore.QPointF(x2, y1),  # 右上
                    QtCore.QPointF(x2, y2),  # 右下
                    QtCore.QPointF(x1, y2),  # 左下
                ]

                self.current.points = points
                self.current.point_labels = [1, 1, 1, 1]
                self.current.fill = False
                
                # 计算宽度和高度
                width = abs(x2 - x1)
                height = abs(y2 - y1)
                
                # 计算中心点
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                self.current.arrow_center = QtCore.QPointF(center_x, center_y)
                
                # 设置初始方向，根据宽高比确定朝向短边还是长边
                if width < height:
                    self.current.direction = 90  # 水平方向（朝向短边）
                else:
                    self.current.direction = 0  # 垂直方向（朝向短边）
                
                # 计算旋转方向向量
                angle_rad = math.radians(self.current.direction)
                dir_vector = QtCore.QPointF(math.cos(angle_rad), math.sin(angle_rad))
                
                # 计算与箭头方向平行的边的长度
                parallel_edge_length = width if self.current.direction == 0 else height
                
                # 计算箭头起始点：从中心点向箭头方向移动平行边长度的一半
                arrow_start_x = center_x + (dir_vector.x() * parallel_edge_length * 0.5)
                arrow_start_y = center_y + (dir_vector.y() * parallel_edge_length * 0.5)
                self.current.arrow_center = QtCore.QPointF(arrow_start_x, arrow_start_y)
                
                # 计算箭头长度：与箭头平行的边的长度的0.3
                arrow_length = parallel_edge_length * 0.3
                
                # 计算箭头终点
                end_x = arrow_start_x + arrow_length * dir_vector.x()
                end_y = arrow_start_y + arrow_length * dir_vector.y()
                self.current.arrow_end = QtCore.QPointF(end_x, end_y)
            else:
                # 如果点不够，取消创建旋转框
                self.current = None
                return

        # 调用父类的finalise方法完成提交
        super().finalise()

        # 如果仍在绘图模式，为下一次绘制准备好line
        if self.createMode == "polygon":
            if self.current is not None:
                self.line.points = [self.current[-1], self.current[0]]
                self.current = None
                self.drawingPolygon.emit(False)
        elif self.createMode == "linestrip":
            self.current = None
            self.drawingPolygon.emit(False)
            self.line.points = []
            self.line.point_labels = []
        else:
            self.current = None
            self.line.points = []
            self.line.point_labels = []
            self.drawingPolygon.emit(False)

    # 添加角度输入对话框方法
    def showAngleInputDialog(self, shape):
        # 此方法已不再需要，应移除
        pass

    # 重写父类的undoLastLine方法，修复取消标签输入后标注残留的问题
    def undoLastLine(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.current.restoreShapeRaw()
        if self.createMode in ["polygon", "linestrip"]:
            self.line.points = [self.current[-1], self.current[0]]
        elif self.createMode in ["rectangle", "line", "circle", "rotation"]:
            self.current.points = self.current.points[0:1]
        elif self.createMode == "point":
            self.current = None
        self.drawingPolygon.emit(True)
        # 保存当前绘制模式，以便在取消操作时能正确处理
        self._lastCreateMode = self.createMode


def polygon_intersects_curve(polygon, curve):
    def point_in_polygon(point, polygon):
        x, y = point
        n = len(polygon)
        inside = False
        p1 = polygon[0]
        for i in range(1, n + 1):
            p2 = polygon[i % n]
            if y > min(p1[1], p2[1]):
                if y <= max(p1[1], p2[1]):
                    if x <= max(p1[0], p2[0]):
                        if p1[1] != p2[1]:
                            xinters = (y - p1[1]) * (p2[0] - p1[0]) / (p2[1] - p1[1]) + p1[0]
                        if p1[0] == p2[0] or x <= xinters:
                            inside = not inside
            p1 = p2
        return inside

    def segments_intersect(p1, p2, p3, p4):
        def ccw(A, B, C):
            return (C[1] - A[1]) * (B[0] - A[0]) - (B[1] - A[1]) * (C[0] - A[0])

        A = p1
        B = p2
        C = p3
        D = p4

        ccw1 = ccw(A, B, C)
        ccw2 = ccw(A, B, D)
        ccw3 = ccw(C, D, A)
        ccw4 = ccw(C, D, B)

        if ((ccw1 * ccw2 < 0) and (ccw3 * ccw4 < 0)):
            return True

        if ccw1 == 0 and is_point_on_segment(A, B, C):
            return True
        if ccw2 == 0 and is_point_on_segment(A, B, D):
            return True
        if ccw3 == 0 and is_point_on_segment(C, D, A):
            return True
        if ccw4 == 0 and is_point_on_segment(C, D, B):
            return True

        return False

    def is_point_on_segment(p1, p2, p):
        return min(p1[0], p2[0]) <= p[0] <= max(p1[0], p2[0]) and min(p1[1], p2[1]) <= p[1] <= max(p1[1], p2[1])

    # 检查曲线点是否在多边形内
    for point in curve:
        if point_in_polygon(point, polygon):
            return True

    # 检查多边形的边是否与曲线相交
    n = len(polygon)
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        for j in range(len(curve) - 1):
            p3 = curve[j]
            p4 = curve[j + 1]
            if segments_intersect(p1, p2, p3, p4):
                return True

    return False

