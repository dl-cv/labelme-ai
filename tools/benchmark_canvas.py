"""Read-only offscreen annotation benchmark against a git revision.

Run with PYTHONPATH pointing at the checkout, for example:
    python tools/benchmark_canvas.py --image sample.jpg --rect 4000 1500 1400 900

Only image/JSON reads are performed. No MainWindow, save path, or user settings
are opened. Timings are microbenchmarks, not end-to-end application frame rates.
"""

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace, ModuleType

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtCore, QtGui, QtWidgets
from pyqtgraph.parametertree import Parameter

from labelme.dlcv.shape import Shape
from labelme.dlcv.shape_render import ShapeRenderSettings
from labelme.dlcv.store import STORE
from labelme.dlcv.zoom_preview import paint_zoom_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--rect", nargs=4, type=float, default=(4000, 1500, 1400, 900),
                        metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"))
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--baseline-ref", default="HEAD")
    parser.add_argument("--zoom-preview", action="store_true",
                        help="also compare full detail and wheel preview at initial zoom scales")
    args = parser.parse_args()
    if args.iterations < 1 or min(args.rect[2:]) <= 0:
        parser.error("iterations and viewport dimensions must be positive")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.excepthook = sys.__excepthook__
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
    if font_path.exists():
        QtGui.QFontDatabase.addApplicationFont(str(font_path))
    root = Parameter.create(name="root", type="group", children=[
        {"name": "other_setting", "type": "group", "children": [
            {"name": "display_shape_label", "type": "bool", "value": True},
            {"name": "shape_label_font_size", "type": "int", "value": 10},
            {"name": "shape_label_position", "type": "str", "value": "center"},
            {"name": "display_shape_center_cross", "type": "bool", "value": False},
            {"name": "shape_center_cross_length", "type": "int", "value": 10},
            {"name": "points_to_crosshair", "type": "bool", "value": False},
        ]},
        {"name": "label_setting", "type": "group", "children": [
            {"name": "display_rotation_arrow", "type": "bool", "value": True},
            {"name": "highlight_start_point", "type": "bool", "value": False},
        ]},
    ])
    STORE.register_main_window(SimpleNamespace(parameter=root))
    # Warm the existing translated label-position property outside the timings.
    STORE.canvas_shape_label_position
    repository = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(
        ["git", "show", f"{args.baseline_ref}:labelme/dlcv/shape.py"],
        cwd=repository, encoding="utf-8",
    )
    baseline = ModuleType("benchmark_baseline_shape")
    exec(compile(source, "<git-baseline-shape>", "exec"), baseline.__dict__)
    data = json.loads(args.image.with_suffix(".json").read_text(encoding="utf-8-sig"))

    def make_shapes(cls):
        for attribute, rgba in (
            ("line_color", (0, 255, 0, 255)), ("fill_color", (0, 255, 0, 64)),
            ("select_line_color", (255, 255, 255, 255)),
            ("select_fill_color", (0, 255, 0, 128)),
            ("vertex_fill_color", (0, 255, 0, 255)),
            ("hvertex_fill_color", (255, 255, 255, 255)),
        ):
            setattr(cls, attribute, QtGui.QColor(*rgba))
        return [cls(label=item["label"], shape_type=item["shape_type"],
                    points=item["points"], direction=item.get("direction", 0))
                for item in data["shapes"]]

    old, new = make_shapes(baseline.Shape), make_shapes(Shape)
    left, top, width, height = args.rect
    target = QtGui.QImage(int(width), int(height), QtGui.QImage.Format_ARGB32_Premultiplied)
    pixmap = QtGui.QPixmap(str(args.image))
    if pixmap.isNull():
        raise ValueError(f"Cannot load image: {args.image}")

    def draw(items, scale, origin, optimized=False, background=False, preview=False):
        painter = QtGui.QPainter(target)
        painter.setFont(QtGui.QFont("Arial", 10))
        painter.translate(-origin[0] * scale, -origin[1] * scale)
        if items:
            type(items[0]).scale = scale
        start = time.perf_counter()
        painted = 0
        if background:
            painter.save()
            painter.scale(scale, scale)
            painter.drawPixmap(0, 0, pixmap)
            painter.restore()
        if optimized or preview:
            settings = ShapeRenderSettings.from_store(scale, painter, STORE)
            viewport = QtCore.QRectF(origin[0] * scale, origin[1] * scale, width, height)
            if preview:
                paint_zoom_preview(painter, items, scale, viewport, settings)
                painted = None
            else:
                cull = not viewport.contains(QtCore.QRectF(
                    0, 0, pixmap.width() * scale, pixmap.height() * scale))
                for shape in items:
                    if not cull or shape.paintBounds(scale, settings).intersects(viewport):
                        shape.paint(painter, settings)
                        painted += 1
        else:
            for shape in items:
                shape.paint(painter)
                painted += 1
        elapsed = (time.perf_counter() - start) * 1000
        painter.end()
        return elapsed, painted

    results = []
    for name, items, scale, origin, optimized, background in (
        ("baseline_overview", old, 0.1, (0, 0), False, False),
        ("optimized_overview", new, 0.1, (0, 0), True, False),
        ("baseline_roi", old, 1.0, (left, top), False, False),
        ("optimized_roi", new, 1.0, (left, top), True, False),
        ("background_overview", [], 0.1, (0, 0), False, True),
        ("background_roi", [], 1.0, (left, top), False, True),
    ):
        draw(items, scale, origin, optimized, background)
        samples = [draw(items, scale, origin, optimized, background)
                   for _ in range(args.iterations)]
        results.append({"case": name, "painted": samples[-1][1],
                        "median_ms": round(statistics.median(x[0] for x in samples), 3)})
    if args.zoom_preview:
        for scale in (0.10, 0.12, 0.16, 0.24, 0.40):
            origin = (max(0, (pixmap.width() - width / scale) / 2),
                      max(0, (pixmap.height() - height / scale) / 2))
            for preview in (False, True):
                draw(new, scale, origin, optimized=True, background=True, preview=preview)
                samples = [draw(new, scale, origin, optimized=True, background=True,
                                preview=preview) for _ in range(args.iterations)]
                results.append({"case": "wheel_preview" if preview else "wheel_full_detail",
                                "scale": scale, "painted": samples[-1][1],
                                "median_ms": round(statistics.median(x[0] for x in samples), 3)})
    print(json.dumps({"shapes": len(new), "image_size": [pixmap.width(), pixmap.height()],
                      "viewport": args.rect, "iterations": args.iterations,
                      "baseline_ref": args.baseline_ref, "results": results},
                     ensure_ascii=False, indent=2))
    return app


if __name__ == "__main__":
    main()
