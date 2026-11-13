"""Cheap frame-local outlines while zooming dense annotation scenes."""

import math

from qtpy import QtCore, QtGui


_OUTLINE_TYPES = {
    "polygon", "rotation", "rectangle", "circle", "line", "linestrip",
    "point", "points",
}
_POINT_RADIUS = 3.0


def paint_zoom_preview(painter, shapes, scale, viewport, settings):
    """Batch unselected outlines in painter-logical pixel coordinates.

    Canvas supplies visible shapes excluding selection/hover, and performs the
    normal detailed draw when wheel interaction stops. No shape or persistent
    geometry cache is modified here. Point annotations retain a small position
    marker; polygon vertices, labels, arrows and fills are intentionally absent.
    """
    groups = {}
    pens = {}
    vleft, vright = viewport.left(), viewport.right()
    vtop, vbottom = viewport.top(), viewport.bottom()

    def flush():
        # Build paths directly from the existing QPointF objects. Scaling the
        # batched draw avoids allocating/scaling four new points per box, while
        # inverse-scaled pen widths preserve screen-space outline thickness.
        painter.save()
        try:
            painter.scale(scale, scale)
            painter.setBrush(QtCore.Qt.NoBrush)
            for key, path in groups.items():
                painter.setPen(pens[key])
                painter.drawPath(path)
        finally:
            painter.restore()
        groups.clear()

    painter.save()
    try:
        for shape in shapes:
            kind = shape.shape_type
            if shape.mask is not None or kind not in _OUTLINE_TYPES:
                # Keep full masks and unfamiliar geometry rather than losing
                # their annotation data in a simplified representation.
                flush()
                painter.save()
                try:
                    shape.paint(painter, settings)
                finally:
                    painter.restore()
                continue
            points = shape.points
            count = len(points)
            if not count or (kind == "rotation" and count < 4):
                continue
            if kind in ("circle", "rectangle") and count < 2:
                continue
            if count == 4:
                p0, p1, p2, p3 = points
                xs = (p0.x(), p1.x(), p2.x(), p3.x())
                ys = (p0.y(), p1.y(), p2.y(), p3.y())
            else:
                xs = [point.x() for point in points]
                ys = [point.y() for point in points]
            left, right = min(xs) * scale, max(xs) * scale
            top, bottom = min(ys) * scale, max(ys) * scale
            radius = None
            if kind == "circle":
                cx, cy = xs[0], ys[0]
                radius = math.hypot(xs[1] - cx, ys[1] - cy)
                left, right = (cx - radius) * scale, (cx + radius) * scale
                top, bottom = (cy - radius) * scale, (cy + radius) * scale
            # Include stroke caps/joins, plus essential point position markers.
            width = shape.PEN_WIDTH
            padding = abs(width) * 2 + 2
            if kind in ("point", "points"):
                padding += _POINT_RADIUS
            if (right + padding < vleft or left - padding > vright
                    or bottom + padding < vtop or top - padding > vbottom):
                continue
            color = shape.line_color
            # QColor is the common fast path. Other QPen constructor inputs
            # may encode styles/brushes, so preserve them without coalescing.
            key = (color.getRgb(), width) if isinstance(color, QtGui.QColor) else id(shape)
            if key not in pens:
                # In particular, preserve this Qt binding's QPen(None) behavior
                # rather than silently replacing missing colors with black.
                pen = QtGui.QPen(color)
                pen.setWidth(width)
                if width:
                    pen.setWidthF(width / scale)
                pens[key] = pen
            path = groups.get(key)
            if path is None:
                path = groups[key] = QtGui.QPainterPath()
            if kind == "rectangle":
                path.addRect(QtCore.QRectF(points[0], points[1]).normalized())
            elif kind == "circle":
                path.addEllipse(points[0], radius, radius)
            elif kind in ("point", "points"):
                marker_points = points[:1] if kind == "point" else points
                marker_radius = _POINT_RADIUS / scale
                for point in marker_points:
                    x, y = point.x(), point.y()
                    path.moveTo(x - marker_radius, y)
                    path.lineTo(x + marker_radius, y)
                    path.moveTo(x, y - marker_radius)
                    path.lineTo(x, y + marker_radius)
            else:
                outline = points[:4] if kind == "rotation" and count != 4 else points
                if kind == "rotation" or (kind == "polygon" and shape.isClosed()):
                    outline = [*outline, points[0]]
                path.addPolygon(QtGui.QPolygonF(outline))
        flush()
    finally:
        painter.restore()
