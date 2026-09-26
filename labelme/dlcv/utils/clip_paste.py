"""Copy/paste 几何：偏移、跟随鼠标、超边裁切。"""

import math

from qtpy import QtCore
from shapely.geometry import LineString
from shapely.geometry import Polygon
from shapely.geometry import box


def format_shape_for_clipboard(shape):
    data = {
        "label": shape.label,
        "points": [(p.x(), p.y()) for p in shape.points],
        "group_id": shape.group_id,
        "description": shape.description,
        "shape_type": shape.shape_type,
        "flags": shape.flags,
        "mask": None if shape.mask is None else shape.mask.tolist(),
    }
    if shape.shape_type == "rotation":
        data["direction"] = getattr(shape, "direction", 0.0)
    return data


def create_shape_from_data(shape_data):
    from labelme.dlcv.shape import Shape

    shape = Shape()
    shape.label = shape_data.get("label", "")
    shape.shape_type = shape_data.get("shape_type", "polygon")
    shape.group_id = shape_data.get("group_id")
    shape.description = shape_data.get("description", "")
    shape.flags = shape_data.get("flags", {})
    points = shape_data.get("points", [])
    for point in points:
        shape.addPoint(QtCore.QPointF(point[0], point[1]))
    if shape.shape_type in ["polygon", "linestrip"] and len(points) > 0:
        shape.close()
    mask_data = shape_data.get("mask")
    if mask_data is not None:
        import numpy as np

        shape.mask = np.array(mask_data)
    if shape.shape_type == "rotation":
        shape.direction = shape_data.get("direction", 0.0)
    return shape


def image_clip_box(max_x, max_y):
    return box(0.0, 0.0, float(max_x), float(max_y))


def point_in_image(x, y, max_x, max_y):
    return 0 <= x <= max_x and 0 <= y <= max_y


def translate_shape(shape, dx, dy):
    for point in shape.points:
        point.setX(point.x() + dx)
        point.setY(point.y() + dy)


def replace_shape_points(shape, coords):
    shape.points = []
    shape.point_labels = []
    for x, y in coords:
        shape.addPoint(QtCore.QPointF(float(x), float(y)))
    if shape.shape_type in ("polygon", "linestrip"):
        shape.close()


def clip_closed_coords(coords, max_x, max_y):
    """裁切闭合多边形到图像内，返回新坐标；完全在外则 None。"""
    if len(coords) < 3:
        return None
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return None
    inter = poly.intersection(image_clip_box(max_x, max_y))
    if inter.is_empty:
        return None
    polys = []
    if inter.geom_type == "Polygon":
        polys = [inter]
    elif inter.geom_type == "MultiPolygon":
        polys = list(inter.geoms)
    elif inter.geom_type == "GeometryCollection":
        for geom in inter.geoms:
            if geom.geom_type == "Polygon":
                polys.append(geom)
            elif geom.geom_type == "MultiPolygon":
                polys.extend(geom.geoms)
    if not polys:
        return None
    largest = max(polys, key=lambda g: g.area)
    if largest.area <= 1e-6:
        return None
    new_coords = list(largest.exterior.coords)
    if len(new_coords) > 1 and new_coords[0] == new_coords[-1]:
        new_coords = new_coords[:-1]
    if len(new_coords) < 3:
        return None
    return new_coords


def clip_open_coords(coords, max_x, max_y):
    """裁切折线到图像内。"""
    if len(coords) < 2:
        x, y = coords[0]
        if point_in_image(x, y, max_x, max_y):
            return coords
        return None
    line = LineString(coords)
    inter = line.intersection(image_clip_box(max_x, max_y))
    if inter.is_empty:
        return None
    if inter.geom_type == "LineString":
        return list(inter.coords)
    if inter.geom_type == "MultiLineString":
        longest = max(inter.geoms, key=lambda g: g.length)
        return list(longest.coords)
    if inter.geom_type == "Point":
        return [(inter.x, inter.y)]
    if inter.geom_type == "GeometryCollection":
        lines = [g for g in inter.geoms if g.geom_type == "LineString"]
        if lines:
            longest = max(lines, key=lambda g: g.length)
            return list(longest.coords)
    return None


def clip_shape_to_image(shape, max_x, max_y):
    """将形状裁切到图像内。完全在外返回 False。"""
    if not shape.points:
        return False

    pts = [(p.x(), p.y()) for p in shape.points]
    inside = all(point_in_image(x, y, max_x, max_y) for x, y in pts)
    shape_type = shape.shape_type

    if shape_type == "point":
        return point_in_image(*pts[0], max_x, max_y)

    if shape_type == "points":
        kept = [p for p in pts if point_in_image(*p, max_x, max_y)]
        if not kept:
            return False
        if len(kept) != len(pts):
            replace_shape_points(shape, kept)
        return True

    if shape_type == "rectangle" and len(pts) >= 2:
        if inside:
            return True
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        cl, cr = max(0.0, left), min(max_x, right)
        ct, cb = max(0.0, top), min(max_y, bottom)
        if cl >= cr or ct >= cb:
            return False
        shape.points[0].setX(cl)
        shape.points[0].setY(ct)
        shape.points[1].setX(cr)
        shape.points[1].setY(cb)
        return True

    if shape_type == "mask" and len(pts) >= 2:
        if inside:
            return True
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        cl, cr = max(0.0, left), min(max_x, right)
        ct, cb = max(0.0, top), min(max_y, bottom)
        if cl >= cr or ct >= cb:
            return False
        if getattr(shape, "mask", None) is not None:
            import numpy as np

            sx1 = int(round(cl - left))
            sy1 = int(round(ct - top))
            sx2 = int(round(cr - left))
            sy2 = int(round(cb - top))
            h, w = shape.mask.shape[:2]
            sx1, sy1 = max(0, sx1), max(0, sy1)
            sx2, sy2 = min(w, sx2), min(h, sy2)
            if sx2 > sx1 and sy2 > sy1:
                shape.mask = np.array(shape.mask[sy1:sy2, sx1:sx2])
        shape.points[0].setX(cl)
        shape.points[0].setY(ct)
        shape.points[1].setX(cr)
        shape.points[1].setY(cb)
        return True

    if shape_type == "circle" and len(pts) >= 2:
        if inside:
            cx, cy = pts[0]
            rx, ry = pts[1]
            radius = math.hypot(rx - cx, ry - cy)
            if (
                cx - radius >= 0
                and cy - radius >= 0
                and cx + radius <= max_x
                and cy + radius <= max_y
            ):
                return True
        from labelme.dlcv.utils.shape import shape_to_points

        poly_pts = shape_to_points(shape)
        coords = [(float(x), float(y)) for x, y in poly_pts]
        new_coords = clip_closed_coords(coords, max_x, max_y)
        if not new_coords:
            return False
        shape.shape_type = "polygon"
        replace_shape_points(shape, new_coords)
        return True

    if shape_type in ("line", "linestrip"):
        if inside:
            return True
        new_coords = clip_open_coords(pts, max_x, max_y)
        if not new_coords:
            return False
        replace_shape_points(shape, new_coords)
        return True

    if inside:
        return True

    if shape_type == "rotation":
        min_x = min(x for x, _ in pts)
        max_shape_x = max(x for x, _ in pts)
        min_y = min(y for _, y in pts)
        max_shape_y = max(y for _, y in pts)
        if (
            len(pts) == 4
            and max_shape_x - min_x <= max_x
            and max_shape_y - min_y <= max_y
        ):
            dx = 0.0
            if min_x < 0:
                dx = -min_x
            elif max_shape_x > max_x:
                dx = max_x - max_shape_x
            dy = 0.0
            if min_y < 0:
                dy = -min_y
            elif max_shape_y > max_y:
                dy = max_y - max_shape_y
            translate_shape(shape, dx, dy)
            return True

    new_coords = clip_closed_coords(pts, max_x, max_y)
    if not new_coords:
        return False
    if shape_type == "rotation":
        shape.shape_type = "polygon"
    replace_shape_points(shape, new_coords)
    return True


def add_offset_to_shape(shape, offset=10):
    """向右下偏移。"""
    if not shape.points:
        return
    translate_shape(shape, offset, offset)


def next_same_image_paste_offset(paste_index, step=5):
    """同图第 N 次粘贴的右下偏移。paste_index 从 1 起：1→5，2→10。"""
    return float(step * paste_index)


def copy_target_is_shapes(selected_shapes):
    """Ctrl+C：有选中形状则复制多边形，否则复制图片。"""
    return bool(selected_shapes)


def compute_paste_delta(
    shapes,
    same_image,
    follow_mouse,
    mouse_xy=None,
    offset=5,
):
    """粘贴前整体平移量 (dx, dy)。

    follow_mouse：整体左上角对齐鼠标。
    同图且不跟随：向右下 offset。
    异图：原坐标。
    """
    if not shapes:
        return 0.0, 0.0
    if follow_mouse:
        if mouse_xy is None:
            return 0.0, 0.0
        union_min_x = min(min(p.x() for p in s.points) for s in shapes)
        union_min_y = min(min(p.y() for p in s.points) for s in shapes)
        return float(mouse_xy[0] - union_min_x), float(mouse_xy[1] - union_min_y)
    if same_image:
        return float(offset), float(offset)
    return 0.0, 0.0


def apply_paste_transform(
    shapes,
    same_image,
    follow_mouse,
    mouse_xy,
    max_x,
    max_y,
    offset=5,
):
    """平移后裁切。返回仍在图内的形状列表。"""
    dx, dy = compute_paste_delta(
        shapes,
        same_image=same_image,
        follow_mouse=follow_mouse,
        mouse_xy=mouse_xy,
        offset=offset,
    )
    if dx or dy:
        for shape in shapes:
            translate_shape(shape, dx, dy)
    return [shape for shape in shapes if clip_shape_to_image(shape, max_x, max_y)]
