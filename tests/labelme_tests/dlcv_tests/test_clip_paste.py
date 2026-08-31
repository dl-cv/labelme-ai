import numpy as np
import pytest

from labelme.dlcv.utils.clip_paste import add_offset_to_shape
from labelme.dlcv.utils.clip_paste import apply_paste_transform
from labelme.dlcv.utils.clip_paste import clip_closed_coords
from labelme.dlcv.utils.clip_paste import clip_open_coords
from labelme.dlcv.utils.clip_paste import clip_shape_to_image
from labelme.dlcv.utils.clip_paste import compute_paste_delta
from labelme.dlcv.utils.clip_paste import copy_target_is_shapes
from labelme.dlcv.utils.clip_paste import create_shape_from_data
from labelme.dlcv.utils.clip_paste import format_shape_for_clipboard
from labelme.dlcv.utils.clip_paste import image_clip_box
from labelme.dlcv.utils.clip_paste import next_same_image_paste_offset
from labelme.dlcv.utils.clip_paste import point_in_image
from labelme.dlcv.utils.clip_paste import translate_shape

IMG_W = 100.0
IMG_H = 80.0


def _pts(shape):
    return [(p.x(), p.y()) for p in shape.points]


def test_copy_target_is_shapes():
    assert copy_target_is_shapes([object()]) is True
    assert copy_target_is_shapes([]) is False
    assert copy_target_is_shapes(None) is False


def test_point_in_image_edges():
    assert point_in_image(0, 0, IMG_W, IMG_H)
    assert point_in_image(IMG_W, IMG_H, IMG_W, IMG_H)
    assert not point_in_image(-0.1, 0, IMG_W, IMG_H)
    assert not point_in_image(0, IMG_H + 1, IMG_W, IMG_H)


def test_clip_closed_coords_partial_right(make_shape):
    coords = [(90, 10), (120, 10), (120, 40), (90, 40)]
    clipped = clip_closed_coords(coords, IMG_W, IMG_H)
    assert clipped is not None
    xs = [c[0] for c in clipped]
    assert max(xs) <= IMG_W + 1e-6
    assert min(xs) >= 90 - 1e-6


def test_clip_closed_coords_fully_outside():
    coords = [(200, 10), (220, 10), (220, 40), (200, 40)]
    assert clip_closed_coords(coords, IMG_W, IMG_H) is None


def test_clip_closed_coords_too_few_points():
    assert clip_closed_coords([(1, 1), (2, 2)], IMG_W, IMG_H) is None


def test_clip_open_coords_line_overhang():
    coords = [(50, 10), (150, 10)]
    clipped = clip_open_coords(coords, IMG_W, IMG_H)
    assert clipped is not None
    assert clipped[0] == (50.0, 10.0)
    assert clipped[-1][0] == pytest.approx(IMG_W)


def test_clip_open_coords_fully_outside():
    assert clip_open_coords([(200, 10), (250, 10)], IMG_W, IMG_H) is None


def test_clip_open_coords_single_inside():
    assert clip_open_coords([(10, 10)], IMG_W, IMG_H) == [(10, 10)]


def test_clip_open_coords_single_outside():
    assert clip_open_coords([(200, 10)], IMG_W, IMG_H) is None


def test_clip_polygon_shape(make_shape):
    shape = make_shape(
        "polygon",
        [(90, 10), (120, 10), (120, 40), (90, 40)],
    )
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    xs = [p.x() for p in shape.points]
    assert max(xs) <= IMG_W + 1e-6


def test_clip_polygon_fully_outside_dropped(make_shape):
    shape = make_shape("polygon", [(200, 10), (220, 10), (220, 40)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_clip_point_inside_and_outside(make_shape):
    inside = make_shape("point", [(10, 10)])
    outside = make_shape("point", [(200, 10)])
    assert clip_shape_to_image(inside, IMG_W, IMG_H) is True
    assert clip_shape_to_image(outside, IMG_W, IMG_H) is False


def test_clip_points_keeps_inside_only(make_shape):
    shape = make_shape("points", [(10, 10), (200, 10), (20, 20)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert len(shape.points) == 2


def test_clip_rectangle_overhang(make_shape):
    shape = make_shape("rectangle", [(80, 10), (150, 40)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert shape.points[0].x() == pytest.approx(80)
    assert shape.points[1].x() == pytest.approx(IMG_W)


def test_clip_rectangle_fully_outside(make_shape):
    shape = make_shape("rectangle", [(200, 10), (250, 40)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_clip_line(make_shape):
    shape = make_shape("line", [(50, 10), (150, 10)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert shape.points[-1].x() == pytest.approx(IMG_W)


def test_clip_empty_shape(make_shape):
    shape = make_shape("polygon", [])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_add_offset_to_shape(make_shape):
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    add_offset_to_shape(shape, offset=5)
    assert _pts(shape) == [(15, 15), (25, 15), (25, 25)]


def test_add_offset_empty_noop(make_shape):
    shape = make_shape("polygon", [])
    add_offset_to_shape(shape, offset=5)
    assert shape.points == []


def test_compute_paste_delta_same_image_offset(make_shape):
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    dx, dy = compute_paste_delta([shape], same_image=True, follow_mouse=False)
    assert (dx, dy) == (5.0, 5.0)


def test_compute_paste_delta_other_image_no_offset(make_shape):
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    dx, dy = compute_paste_delta([shape], same_image=False, follow_mouse=False)
    assert (dx, dy) == (0.0, 0.0)


def test_compute_paste_delta_follow_mouse_top_left(make_shape):
    shape = make_shape("polygon", [(10, 20), (30, 20), (30, 40)])
    dx, dy = compute_paste_delta(
        [shape],
        same_image=True,
        follow_mouse=True,
        mouse_xy=(50, 60),
    )
    assert (dx, dy) == (40.0, 40.0)


def test_next_same_image_paste_offset_accumulates():
    assert next_same_image_paste_offset(1) == 5.0
    assert next_same_image_paste_offset(2) == 10.0
    assert next_same_image_paste_offset(3) == 15.0


def test_apply_paste_same_image_second_paste_more_offset(make_shape):
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    kept = apply_paste_transform(
        [shape],
        same_image=True,
        follow_mouse=False,
        mouse_xy=None,
        max_x=IMG_W,
        max_y=IMG_H,
        offset=next_same_image_paste_offset(2),
    )
    assert _pts(kept[0]) == [(20, 20), (30, 20), (30, 30)]


def test_apply_paste_same_image_offset_then_clip(make_shape):
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    kept = apply_paste_transform(
        [shape],
        same_image=True,
        follow_mouse=False,
        mouse_xy=None,
        max_x=IMG_W,
        max_y=IMG_H,
        offset=5,
    )
    assert len(kept) == 1
    assert _pts(kept[0]) == [(15, 15), (25, 15), (25, 25)]


def test_apply_paste_other_image_keeps_coords(make_shape):
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    kept = apply_paste_transform(
        [shape],
        same_image=False,
        follow_mouse=False,
        mouse_xy=None,
        max_x=IMG_W,
        max_y=IMG_H,
    )
    assert _pts(kept[0]) == [(10, 10), (20, 10), (20, 20)]


def test_apply_paste_follow_mouse_then_clip_overflow(make_shape):
    shape = make_shape("polygon", [(0, 0), (40, 0), (40, 40), (0, 40)])
    kept = apply_paste_transform(
        [shape],
        same_image=False,
        follow_mouse=True,
        mouse_xy=(80, 60),
        max_x=IMG_W,
        max_y=IMG_H,
    )
    assert len(kept) == 1
    xs = [p.x() for p in kept[0].points]
    ys = [p.y() for p in kept[0].points]
    assert max(xs) <= IMG_W + 1e-6
    assert max(ys) <= IMG_H + 1e-6
    assert min(p.x() for p in kept[0].points) == pytest.approx(80)


def test_apply_paste_all_outside_dropped(make_shape):
    shape = make_shape("polygon", [(200, 10), (220, 10), (220, 40)])
    kept = apply_paste_transform(
        [shape],
        same_image=False,
        follow_mouse=False,
        mouse_xy=None,
        max_x=IMG_W,
        max_y=IMG_H,
    )
    assert kept == []


def test_clipboard_roundtrip_polygon(real_shape):
    shape = real_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    shape.label = "cat"
    shape.group_id = 3
    shape.description = "d"
    shape.flags = {"a": True}
    data = format_shape_for_clipboard(shape)
    restored = create_shape_from_data(data)
    assert restored.label == "cat"
    assert restored.group_id == 3
    assert restored.description == "d"
    assert restored.flags == {"a": True}
    assert restored.shape_type == "polygon"
    assert _pts(restored) == [(10, 10), (20, 10), (20, 20)]


def test_clipboard_roundtrip_rotation(real_shape):
    shape = real_shape("rotation", [(10, 10), (30, 10), (30, 30), (10, 30)])
    shape.direction = 45.0
    data = format_shape_for_clipboard(shape)
    assert data["direction"] == 45.0
    restored = create_shape_from_data(data)
    assert restored.direction == 45.0


def test_translate_shape(make_shape):
    shape = make_shape("polygon", [(1, 2), (3, 4)])
    translate_shape(shape, 10, -1)
    assert _pts(shape) == [(11, 1), (13, 3)]


def test_image_clip_box_bounds():
    b = image_clip_box(IMG_W, IMG_H)
    assert b.bounds == (0.0, 0.0, IMG_W, IMG_H)


def test_compute_paste_delta_empty_and_follow_without_mouse(make_shape):
    assert compute_paste_delta([], same_image=True, follow_mouse=False) == (0.0, 0.0)
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    assert compute_paste_delta(
        [shape], same_image=True, follow_mouse=True, mouse_xy=None
    ) == (0.0, 0.0)


def test_clip_mask_overhang(make_shape):
    mask = np.ones((30, 70), dtype=np.uint8)
    shape = make_shape("mask", [(80, 10), (150, 40)], mask=mask)
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert shape.points[1].x() == pytest.approx(IMG_W)


def test_clip_mask_fully_outside(make_shape):
    shape = make_shape("mask", [(200, 10), (250, 40)], mask=np.ones((10, 10)))
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_clip_circle_inside_disk(make_shape):
    shape = make_shape("circle", [(40, 40), (50, 40)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert shape.shape_type == "circle"


def test_clip_circle_overflow_becomes_polygon(real_shape):
    shape = real_shape("circle", [(90, 40), (120, 40)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert shape.shape_type == "polygon"


def test_clip_rotation_overflow_becomes_polygon(make_shape):
    shape = make_shape("rotation", [(90, 10), (120, 10), (120, 40), (90, 40)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert shape.shape_type == "polygon"


def test_clip_invalid_bowtie_closed():
    coords = [(0, 0), (40, 40), (40, 0), (0, 40)]
    clipped = clip_closed_coords(coords, IMG_W, IMG_H)
    assert clipped is None or len(clipped) >= 3


def test_clipboard_roundtrip_with_mask(real_shape):
    shape = real_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    shape.mask = np.ones((3, 3), dtype=np.uint8)
    data = format_shape_for_clipboard(shape)
    restored = create_shape_from_data(data)
    assert restored.mask.shape == (3, 3)


def test_clip_open_reenter_keeps_longest_segment():
    # 出图再入图 → MultiLineString，取最长段
    coords = [(-20, 10), (10, 10), (10, -20), (90, -20), (90, 10), (150, 10)]
    clipped = clip_open_coords(coords, IMG_W, IMG_H)
    assert clipped is not None
    assert all(0 <= x <= IMG_W and 0 <= y <= IMG_H for x, y in clipped)


def test_clip_circle_fully_outside_dropped(real_shape):
    shape = real_shape("circle", [(400, 400), (410, 400)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_clip_points_all_outside(make_shape):
    shape = make_shape("points", [(200, 10), (210, 10)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_clip_linestrip_inside_unchanged(make_shape):
    pts = [(10, 10), (20, 20), (30, 10)]
    shape = make_shape("linestrip", pts)
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert _pts(shape) == pts


def test_clip_polygon_inside_unchanged(make_shape):
    pts = [(10, 10), (20, 10), (20, 20)]
    shape = make_shape("polygon", pts)
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert _pts(shape) == pts


def test_clip_rectangle_inside_unchanged(make_shape):
    pts = [(10, 10), (40, 40)]
    shape = make_shape("rectangle", pts)
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert _pts(shape) == pts


def test_clip_mask_inside_unchanged(make_shape):
    pts = [(10, 10), (40, 40)]
    shape = make_shape("mask", pts, mask=np.ones((30, 30), dtype=np.uint8))
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is True
    assert _pts(shape) == pts


def test_clip_line_fully_outside(make_shape):
    shape = make_shape("line", [(200, 10), (250, 10)])
    assert clip_shape_to_image(shape, IMG_W, IMG_H) is False


def test_clip_tiny_sliver_closed_none():
    # 与图像几乎不相交的极细条
    coords = [(100.0000005, 10), (100.0000006, 10), (100.0000006, 11)]
    assert clip_closed_coords(coords, IMG_W, IMG_H) is None


def test_clip_open_empty_intersection():
    assert clip_open_coords([(200, 200), (250, 250)], IMG_W, IMG_H) is None


def test_replace_keeps_polygon_close(make_shape):
    from labelme.dlcv.utils.clip_paste import replace_shape_points

    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    replace_shape_points(shape, [(1, 1), (2, 1), (2, 2)])
    assert len(shape.points) == 3
    shape = make_shape("polygon", [(10, 10), (20, 10), (20, 20)])
    kept = apply_paste_transform(
        [shape],
        same_image=False,
        follow_mouse=True,
        mouse_xy=None,
        max_x=IMG_W,
        max_y=IMG_H,
    )
    assert _pts(kept[0]) == [(10, 10), (20, 10), (20, 20)]

