# 属性查看方法
import math
from PyQt5 import QtCore, QtWidgets, QtGui
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

# 计算窗口显示位置
def get_window_position(center_point, canvas, window_width, window_height, offset=0):
    """
    根据形状中心点计算属性窗口的左上角全局坐标，使属性窗口中心与该点对齐。
    若越界，尽量保持在屏幕内（左/上边界），右/下边界由调用处再校正。
    """
    try:
        # 1) 画布(图像)坐标 -> 画布部件坐标
        # 逆 transformPos：widget = (image + offsetToCenter + offset) * scale
        scale = getattr(canvas, "scale", 1.0) or 1.0
        offset_to_center = canvas.offsetToCenter()
        canvas_offset = getattr(canvas, "offset", QtCore.QPointF(0, 0))

        widget_x = int((center_point.x() + offset_to_center.x() + canvas_offset.x()) * scale)
        widget_y = int((center_point.y() + offset_to_center.y() + canvas_offset.y()) * scale)

        # 2) 画布部件坐标 -> 全局屏幕坐标（中心点）
        center_global = canvas.mapToGlobal(QtCore.QPoint(widget_x, widget_y))

        # 3) 对话框中心对齐该点 -> 计算左上角
        x = int(center_global.x() - window_width / 2)
        y = int(center_global.y() - window_height / 2)

        # 4) 可选偏移（正值向右下偏移）
        if offset:
            try:
                if isinstance(offset, (int, float)):
                    x += int(offset)
                    y += int(offset)
                elif hasattr(offset, "x") and hasattr(offset, "y"):
                    x += int(offset.x())
                    y += int(offset.y())
            except Exception:
                pass

        # 5) 限制到所在屏幕左/上边界，防止完全飞出左上角
        screen = QtWidgets.QApplication.screenAt(center_global) if hasattr(QtWidgets.QApplication, "screenAt") else None
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            sg = screen.geometry()
            x = max(x, sg.left())
            y = max(y, sg.top())

        return x, y
    except Exception:
        # 退化：如计算失败，直接返回中心点整数（可能是相对坐标，由调用方兜底）
        return int(center_point.x()), int(center_point.y())

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

        # ESC 快捷键关闭窗口
        esc_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self)
        esc_shortcut.activated.connect(self.close)
