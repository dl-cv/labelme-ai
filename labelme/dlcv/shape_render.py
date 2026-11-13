"""Frame-local shape drawing options; geometry is deliberately not cached here."""

from dataclasses import dataclass, field

from qtpy import QtGui

from labelme.dlcv.store import STORE


@dataclass(frozen=True)
class ShapeRenderSettings:
    canvas_display_shape_label: bool
    canvas_shape_label_font_size: int
    canvas_shape_label_position: str
    canvas_display_rotation_arrow: bool
    canvas_points_to_crosshair: bool
    canvas_display_shape_center_cross: bool
    canvas_shape_center_cross_length: float
    canvas_highlight_start_point: bool
    label_font: QtGui.QFont
    label_font_metrics: QtGui.QFontMetrics
    # 只在本帧复用同名标签尺寸，字体、DPI或设置变化会创建新快照。
    label_sizes: dict = field(default_factory=dict, compare=False)

    @classmethod
    def from_store(cls, scale, painter=None, store=None):
        """Read STORE once per frame, including font metrics for the paint device.

        Pass the same snapshot to ``paintBounds`` and ``paint`` at this scale.
        The optional painter supplies the font family and device DPI; neither
        this factory nor shape painting changes the caller's font.
        """
        if store is None:
            store = STORE
        display_label = store.canvas_display_shape_label
        font_size = store.canvas_shape_label_font_size
        position = store.canvas_shape_label_position
        arrow = getattr(store, "canvas_display_rotation_arrow", True)
        points_to_crosshair = store.canvas_points_to_crosshair
        center_cross = store.canvas_display_shape_center_cross
        cross_length = store.canvas_shape_center_cross_length
        highlight_start = store.canvas_highlight_start_point
        font = QtGui.QFont(painter.font() if painter is not None else QtGui.QFont())
        font.setBold(True)
        font.setPointSize(font_size if scale < 1 else max(1, int(font_size * scale)))
        metrics = (
            QtGui.QFontMetrics(font, painter.device())
            if painter is not None else QtGui.QFontMetrics(font)
        )
        return cls(
            display_label, font_size, position, arrow, points_to_crosshair,
            center_cross, cross_length, highlight_start, font, metrics,
        )
