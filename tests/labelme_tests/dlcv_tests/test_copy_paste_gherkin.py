from pytest_bdd import given
from pytest_bdd import parsers
from pytest_bdd import scenarios
from pytest_bdd import then
from pytest_bdd import when

from labelme.dlcv.utils.clip_paste import apply_paste_transform
from labelme.dlcv.utils.clip_paste import copy_target_is_shapes

from .conftest import DummyShape

scenarios("copy_paste_polygon.feature")

IMG_W = 100.0
IMG_H = 80.0


@given("画布上有选中的多边形", target_fixture="copy_ctx")
def selected_shapes():
    return {"selected": [object()]}


@given("画布上没有选中的多边形", target_fixture="copy_ctx")
def no_selected_shapes():
    return {"selected": []}


@when("用户按下 Ctrl+C")
def press_ctrl_c(copy_ctx):
    copy_ctx["copy_shapes"] = copy_target_is_shapes(copy_ctx["selected"])


@then("复制目标是多边形")
def copy_is_polygon(copy_ctx):
    assert copy_ctx["copy_shapes"] is True


@then("复制目标是图片")
def copy_is_image(copy_ctx):
    assert copy_ctx["copy_shapes"] is False


@given("剪贴板中有来自当前图像的多边形", target_fixture="paste_ctx")
def clipboard_same_image():
    shape = DummyShape("polygon", [(10, 10), (20, 10), (20, 20)])
    return {
        "shapes": [shape],
        "same_image": True,
        "follow_mouse": False,
        "mouse_xy": None,
        "kept": None,
    }


@given("剪贴板中有来自其他图像的多边形", target_fixture="paste_ctx")
def clipboard_other_image():
    shape = DummyShape("polygon", [(10, 10), (20, 10), (20, 20)])
    return {
        "shapes": [shape],
        "same_image": False,
        "follow_mouse": False,
        "mouse_xy": None,
        "kept": None,
    }


@given("剪贴板中有超出当前图像的多边形", target_fixture="paste_ctx")
def clipboard_overflow():
    shape = DummyShape("polygon", [(90, 10), (120, 10), (120, 40), (90, 40)])
    return {
        "shapes": [shape],
        "same_image": False,
        "follow_mouse": False,
        "mouse_xy": None,
        "kept": None,
    }


@given("剪贴板中有完全位于图像外的多边形", target_fixture="paste_ctx")
def clipboard_outside():
    shape = DummyShape("polygon", [(200, 10), (220, 10), (220, 40)])
    return {
        "shapes": [shape],
        "same_image": False,
        "follow_mouse": False,
        "mouse_xy": None,
        "kept": None,
    }


@given("剪贴板中有多边形", target_fixture="paste_ctx")
def clipboard_any():
    shape = DummyShape("polygon", [(10, 20), (30, 20), (30, 40), (10, 40)])
    return {
        "shapes": [shape],
        "same_image": False,
        "follow_mouse": False,
        "mouse_xy": None,
        "kept": None,
    }


@given("复制多边形跟随鼠标已关闭")
def follow_mouse_off(paste_ctx):
    paste_ctx["follow_mouse"] = False


@given("复制多边形跟随鼠标已开启")
def follow_mouse_on(paste_ctx):
    paste_ctx["follow_mouse"] = True


@given(parsers.parse("鼠标位于图像坐标 {x:d},{y:d}"))
def mouse_at(paste_ctx, x, y):
    paste_ctx["mouse_xy"] = (x, y)


def _run_paste(paste_ctx):
    paste_ctx["kept"] = apply_paste_transform(
        paste_ctx["shapes"],
        same_image=paste_ctx["same_image"],
        follow_mouse=paste_ctx["follow_mouse"],
        mouse_xy=paste_ctx["mouse_xy"],
        max_x=IMG_W,
        max_y=IMG_H,
        offset=5,
    )


@when("用户在同一张图按下 Ctrl+V")
def paste_same(paste_ctx):
    _run_paste(paste_ctx)


@when("用户在当前图按下 Ctrl+V")
def paste_current(paste_ctx):
    _run_paste(paste_ctx)


@when("用户按下 Ctrl+V")
def paste_any(paste_ctx):
    _run_paste(paste_ctx)


@then("多边形向右下偏移 5 像素")
def offset_5(paste_ctx):
    pts = [(p.x(), p.y()) for p in paste_ctx["kept"][0].points]
    assert pts == [(15, 15), (25, 15), (25, 25)]


@then("多边形仍在图像内")
def still_inside(paste_ctx):
    for shape in paste_ctx["kept"]:
        for p in shape.points:
            assert 0 <= p.x() <= IMG_W
            assert 0 <= p.y() <= IMG_H


@then("多边形保持原坐标")
def original_coords(paste_ctx):
    pts = [(p.x(), p.y()) for p in paste_ctx["kept"][0].points]
    assert pts == [(10, 10), (20, 10), (20, 20)]


@then("多边形被裁切到图像边界内")
def clipped_inside(paste_ctx):
    assert paste_ctx["kept"]
    for shape in paste_ctx["kept"]:
        for p in shape.points:
            assert 0 <= p.x() <= IMG_W + 1e-6
            assert 0 <= p.y() <= IMG_H + 1e-6
        assert max(p.x() for p in shape.points) <= IMG_W + 1e-6


@then("没有形状被粘贴")
def nothing_pasted(paste_ctx):
    assert paste_ctx["kept"] == []


@then("多边形左上角对齐鼠标")
def top_left_follows_mouse(paste_ctx):
    shape = paste_ctx["kept"][0]
    min_x = min(p.x() for p in shape.points)
    min_y = min(p.y() for p in shape.points)
    assert min_x == paste_ctx["mouse_xy"][0]
    assert min_y == paste_ctx["mouse_xy"][1]
