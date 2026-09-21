"""多边形复制和粘贴的位置计算。"""

import math
import os

from shapely.geometry import Polygon


class CopyPasteError(ValueError):
    """复制或粘贴的数据无法按要求处理。"""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def normalize_image_path(path):
    if not path:
        return ""
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def is_same_image(source_path, target_path):
    source = normalize_image_path(source_path)
    target = normalize_image_path(target_path)
    return bool(source and target and source == target)


def shape_points(shape):
    return [(float(point.x()), float(point.y())) for point in shape.points]


def validate_shape(shape):
    points = shape_points(shape)
    if not points or any(
        not math.isfinite(value) for point in points for value in point
    ):
        raise CopyPasteError("invalid")

    if shape.shape_type == "polygon":
        if len(points) < 3:
            raise CopyPasteError("invalid")
        polygon = Polygon(points)
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise CopyPasteError("invalid")
    return points


def validate_shapes(shapes):
    if not shapes:
        raise CopyPasteError("empty")
    for shape in shapes:
        validate_shape(shape)


def shapes_bounds(shapes):
    validate_shapes(shapes)
    points = [point for shape in shapes for point in shape_points(shape)]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def fit_translation(bounds, max_x, max_y, requested_dx=0.0, requested_dy=0.0):
    min_x, min_y, right, bottom = bounds
    max_x = float(max_x)
    max_y = float(max_y)
    if max_x <= 0 or max_y <= 0:
        raise CopyPasteError("image_missing")

    if right - min_x > max_x or bottom - min_y > max_y:
        raise CopyPasteError("too_large")

    min_dx = -min_x
    max_dx = max_x - right
    min_dy = -min_y
    max_dy = max_y - bottom
    dx = min(max(float(requested_dx), min_dx), max_dx)
    dy = min(max(float(requested_dy), min_dy), max_dy)
    return dx, dy


def placement_translation(
    shapes,
    *,
    same_image,
    follow_cursor,
    cursor_xy,
    max_x,
    max_y,
    offset,
):
    bounds = shapes_bounds(shapes)
    min_x, min_y, _, _ = bounds
    if follow_cursor:
        if cursor_xy is None:
            raise CopyPasteError("cursor_missing")
        requested_dx = float(cursor_xy[0]) - min_x
        requested_dy = float(cursor_xy[1]) - min_y
    elif same_image:
        requested_dx = float(offset)
        requested_dy = float(offset)
    else:
        requested_dx = 0.0
        requested_dy = 0.0

    dx, dy = fit_translation(
        bounds,
        max_x=max_x,
        max_y=max_y,
        requested_dx=requested_dx,
        requested_dy=requested_dy,
    )
    if same_image and not follow_cursor and abs(dx) < 1e-9 and abs(dy) < 1e-9:
        dx, dy = fit_translation(
            bounds,
            max_x=max_x,
            max_y=max_y,
            requested_dx=-float(offset),
            requested_dy=-float(offset),
        )
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            raise CopyPasteError("cannot_offset")
    return dx, dy


def translate_shapes(shapes, dx, dy):
    if not dx and not dy:
        return
    for shape in shapes:
        for point in shape.points:
            point.setX(point.x() + dx)
            point.setY(point.y() + dy)


def move_shape_inside_image(shape, max_x, max_y):
    bounds = shapes_bounds([shape])
    dx, dy = fit_translation(bounds, max_x=max_x, max_y=max_y)
    translate_shapes([shape], dx, dy)
    return dx, dy
