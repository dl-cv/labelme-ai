import pytest
from qtpy import QtCore


class DummyShape:
    """轻量 Shape，不依赖 labelme.dlcv.shape。"""

    def __init__(self, shape_type="polygon", points=None, mask=None):
        self.shape_type = shape_type
        self.points = []
        self.point_labels = []
        self.mask = mask
        self.label = None
        self.group_id = None
        self.description = None
        self.flags = {}
        self.direction = 0.0
        if points:
            for x, y in points:
                self.addPoint(QtCore.QPointF(float(x), float(y)))

    def addPoint(self, point, label=1):
        self.points.append(point)
        self.point_labels.append(label)

    def close(self):
        pass

    def get_points_pos(self):
        return [[p.x(), p.y()] for p in self.points]


@pytest.fixture
def make_shape():
    def _make(shape_type="polygon", points=None, mask=None):
        return DummyShape(shape_type=shape_type, points=points, mask=mask)

    return _make


@pytest.fixture
def real_shape():
    def _make(shape_type="polygon", points=None):
        from labelme.dlcv.shape import Shape

        shape = Shape(shape_type=shape_type)
        if points:
            for x, y in points:
                shape.addPoint(QtCore.QPointF(float(x), float(y)))
            if shape_type in ("polygon", "linestrip"):
                shape.close()
        return shape

    return _make
