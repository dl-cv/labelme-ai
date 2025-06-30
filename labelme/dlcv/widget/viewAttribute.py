# 属性查看方法
import math
from shapely.geometry import Polygon

def get_shape_attribute(shape):
    """
    输入：shape对象
    输出：字典，包含宽度、高度、面积
    """
    points = shape.points
    n = len(points)
    if n < 2:
        return {"width": 0, "height": 0, "area": 0}

    # 1. 计算所有点的x、y坐标
    xs = [p.x() for p in points]
    ys = [p.y() for p in points]

    # 2. 计算宽度和高度（包围盒）
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    # 3. 计算面积
    area = 0
    if n >= 3:
        # 多边形、旋转框、矩形
        try:
            poly = Polygon([(p.x(), p.y()) for p in points])
            area = abs(poly.area)
        except Exception:
            area = 0
    elif n == 2 and shape.shape_type == "circle":
        # 圆：点0为圆心，点1为圆周上一点
        r = math.hypot(points[0].x() - points[1].x(), points[0].y() - points[1].y())
        width = height = r * 2
        area = math.pi * r * r

    return {
        "width": round(width, 2),
        "height": round(height, 2),
        "area": round(area, 2)
    }