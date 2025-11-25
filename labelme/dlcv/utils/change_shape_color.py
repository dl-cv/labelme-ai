"""修改形状颜色的功能模块"""
import html
from typing import TYPE_CHECKING

from qtpy import QtGui

from labelme.dlcv import dlcv_tr
from labelme.logger import logger
from labelme import utils

if TYPE_CHECKING:
    from labelme.dlcv.app import MainWindow


def init_change_color_action(main_window: 'MainWindow'):
    """初始化修改颜色action并添加到右键菜单
    
    Args:
        main_window: MainWindow实例
    """
    action = utils.newAction(
        main_window,
        dlcv_tr("change color"),
        lambda: change_shape_color(main_window),
        None,
        "color",
        dlcv_tr("change the color of the selected polygon"),
        enabled=False,
    )
    
    # 保存action为实例变量，以便在其他地方访问
    main_window.actions.changeColor = action
    
    # 确保菜单已创建
    if not hasattr(main_window, 'menus') or not hasattr(main_window.menus, 'labelList'):
        logger.warning("菜单未创建，无法添加修改颜色action")
        return
    
    # 将action插入到编辑和删除之间
    existing_actions = main_window.menus.labelList.actions()
    if len(existing_actions) >= 2:
        # 在编辑（第0个）和删除（第1个）之间插入
        main_window.menus.labelList.insertAction(existing_actions[1], action)
    else:
        # 如果没有现有actions，直接添加
        main_window.menus.labelList.addAction(action)
    
    return action


def change_shape_color(main_window: 'MainWindow'):
    """更改选中形状的颜色
    
    Args:
        main_window: MainWindow实例
    """
    items = main_window.labelList.selectedItems()
    if not items:
        return
    
    # 获取第一个选中形状的当前颜色
    shape = items[0].shape()
    current_color = shape.fill_color
    
    # 打开颜色选择对话框
    from labelme.widgets import ColorDialog
    color_dialog = ColorDialog(main_window)
    new_color = color_dialog.getColor(
        value=current_color,
        title="选择颜色",
        default=current_color
    )
    
    if new_color is None:
        return
    
    # 获取RGB值
    r, g, b = new_color.getRgb()[:3]
    rgb = (r, g, b)
    
    # 确保配置支持手动颜色模式
    if main_window._config["shape_color"] != "manual":
        main_window._config["shape_color"] = "manual"
    
    # 更新配置中的 label_colors
    if main_window._config["label_colors"] is None:
        main_window._config["label_colors"] = {}
    
    # 更新所有选中形状的标签颜色
    labels_to_update = set()
    for item in items:
        shape = item.shape()
        label = shape.label
        labels_to_update.add(label)
        # 保存颜色到配置
        main_window._config["label_colors"][label] = rgb
        # 更新形状颜色
        update_shape_color_with_rgb(shape, rgb)
        # 更新列表项显示
        text = shape.label if shape.group_id is None else "{} ({})".format(shape.label, shape.group_id)
        item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                html.escape(text), r, g, b
            )
        )
    
    # 更新 uniqLabelList 中标签的显示颜色
    for label in labels_to_update:
        item = main_window.uniqLabelList.findItemByLabel(label)
        if item:
            main_window.uniqLabelList.setItemLabel(item, label, rgb)
    
    # 更新画布显示
    main_window.setDirty()
    main_window.canvas.repaint()
    main_window.canvas.update()


def update_shape_color_with_rgb(shape, rgb):
    """使用指定的RGB值更新形状颜色
    
    Args:
        shape: Shape对象
        rgb: RGB元组 (r, g, b)
    """
    r, g, b = rgb
    shape.line_color = QtGui.QColor(r, g, b)
    shape.vertex_fill_color = QtGui.QColor(r, g, b)
    shape.hvertex_fill_color = QtGui.QColor(255, 255, 255)
    shape.fill_color = QtGui.QColor(r, g, b, 128)
    shape.select_line_color = QtGui.QColor(255, 255, 255)
    shape.select_fill_color = QtGui.QColor(r, g, b, 155)
