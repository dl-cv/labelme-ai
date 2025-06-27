import copy
import math

import numpy as np

from labelme.dlcv.shape import Shape


def shape_to_points(shape: dict or Shape):
    new_points = []
    try:
        # 从 Json 中读取的数据
        shape_type = shape['shape_type']
        points = shape['points']
    except:
        # Labelme 中的 Shape 对象
        shape_type = shape.shape_type
        points = shape.get_points_pos()
    if shape_type == 'polygon':
        new_points = points
        if len(points) < 3:
            new_points = []
            print('polygon 异常，少于三个点', shape)
    elif shape_type in ['line', 'linestrip']:
        if len(points) > 2:
            new_points = copy.deepcopy(points)
            for p in reversed(points):
                new_points.append(p)
        else:
            new_points = points
    elif shape_type == 'rectangle':
        (x1, y1), (x2, y2) = points
        x1, x2 = sorted([x1, x2])
        y1, y2 = sorted([y1, y2])
        new_points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    elif shape_type == "circle":
        # Create polygon shaped based on connecting lines from/to following degress
        bearing_angles = [
            0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210,
            225, 240, 255, 270, 285, 300, 315, 330, 345, 360
        ]

        orig_x1 = points[0][0]
        orig_y1 = points[0][1]

        orig_x2 = points[1][0]
        orig_y2 = points[1][1]

        # Calculate radius of circle
        radius = math.sqrt((orig_x2 - orig_x1) ** 2 + (orig_y2 - orig_y1) ** 2)

        circle_polygon = []

        for i in range(0, len(bearing_angles) - 1):
            ad1 = math.radians(bearing_angles[i])
            x1 = radius * math.cos(ad1)
            y1 = radius * math.sin(ad1)
            circle_polygon.append((orig_x1 + x1, orig_y1 + y1))

            ad2 = math.radians(bearing_angles[i + 1])
            x2 = radius * math.cos(ad2)
            y2 = radius * math.sin(ad2)
            circle_polygon.append((orig_x1 + x2, orig_y1 + y2))

        new_points = circle_polygon
    elif shape_type in ['point']:
        new_points = points
    else:
        print('未知 shape_type', shape['shape_type'])

    new_points = np.asarray(new_points, dtype=np.int32)
    return new_points
