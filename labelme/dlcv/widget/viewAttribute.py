# 属性查看方法
import math
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import QPointF
from qtpy import QtWidgets
from shapely.geometry import Polygon
from labelme.dlcv.shape import Shape,ShapeType



def get_shape_attribute(shape:Shape):
    """
    输入：shape对象
    输出：字典，包含宽度、高度、面积
    """
    points = shape.points
    n = len(points)

    # 计算所有点的x、y坐标
    xs = [p.x() for p in points]
    ys = [p.y() for p in points]
    width = height = area = 0

    if shape.shape_type == ShapeType.ROTATION or shape.shape_type == ShapeType.POLYGON:
        # 旋转框和多边形: 使用多边形面积计算
        try:
            poly = Polygon([(p.x(), p.y()) for p in points])
            area = abs(poly.area)
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
        except Exception:
            pass

    elif shape.shape_type == ShapeType.RECTANGLE:
        # 矩形: 两个对角点
        width = abs(points[1].x() - points[0].x())
        height = abs(points[1].y() - points[0].y())
        area = width * height

    elif shape.shape_type == ShapeType.CIRCLE and n == 2:
        # 圆: 点0为圆心,点1为圆周上一点
        r = math.hypot(points[0].x() - points[1].x(), points[0].y() - points[1].y())
        width = height = r * 2
        area = math.pi * r * r

    elif shape.shape_type == ShapeType.POINTS:
        # 点集: 计算外接矩形
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        area = 0

    return {
        "width": round(width, 2),
        "height": round(height, 2),
        "area": round(area, 2)
    }

def get_window_position(shape, canvas, window_width, window_height, offset=0):
    """
    获取标注框右下角在屏幕上的坐标（窗口中心对齐右下角）
    """
    points = shape.points
    x = max([p.x() for p in points])
    y = max([p.y() for p in points])
    canvas_global = canvas.mapToGlobal(QtCore.QPoint(0, 0))
    # 让窗口中心点对齐shape右下角 
    screen_x = int(canvas_global.x() + x - window_width // 2 + offset)
    screen_y = int(canvas_global.y() + y - window_height // 2 + offset)
    return screen_x, screen_y

# ------------ 属性展示窗口类 ------------
class viewAttribute(QtWidgets.QWidget):
    # 传入宽度、高度、面积， 然后以组件形式展示对象属性
    def __init__(self, width=0, height=0, area=0, parent=None):
        super().__init__(parent)
        self.width = width
        self.height = height 
        self.area = area
        
        # 创建布局
        layout = QtWidgets.QVBoxLayout()
        
        # 创建标签显示属性
        width_label = QtWidgets.QLabel(f"宽度: {self.width} pixels")
        height_label = QtWidgets.QLabel(f"高度: {self.height} pixels") 
        area_label = QtWidgets.QLabel(f"面积: {self.area} pixels")
        
        # 添加标签到布局
        layout.addWidget(width_label)
        layout.addWidget(height_label)
        layout.addWidget(area_label)
        
        self.setLayout(layout)
