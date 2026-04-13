import html
from typing import Callable

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt

from labelme import utils
from labelme.app import MainWindow
from labelme.dlcv import dlcv_tr
from labelme.utils.qt import newIcon


def init_uniq_label_list_text_flag_wgt(window: "MainWindow",
                                       add_text_flag: Callable):
    if not hasattr(window.actions, "changeColor"):
        init_change_color_action(window)

    def uniqLabelList_item_double_clicked_callback(
            item: QtWidgets.QListWidgetItem):
        """双击 uniqLabelList 时, 设置 text_flag"""
        if window.get_text_flag():
            window.set_text_flag(item.data(Qt.UserRole))
            window.canvas.shapeMoved.emit()
        else:
            add_text_flag()

    # uniqLabelList 双击后设置 text_flag
    window.uniqLabelList.itemDoubleClicked.connect(
        uniqLabelList_item_double_clicked_callback)

    # 为 uniqLabelList 添加右键菜单删除功能
    def show_uniq_label_menu(pos: QtCore.QPoint):
        menu = QtWidgets.QMenu()
        delete_action = QtWidgets.QAction(dlcv_tr("删除标签"), window)
        delete_action.setIcon(newIcon("delete"))
        menu.addAction(delete_action)
        if hasattr(window.actions, "changeColor"):
            menu.addAction(window.actions.changeColor)

        def delete_uniq_label():
            selected_items = window.uniqLabelList.selectedItems()
            if not selected_items:
                return

            # 删除前询问确认
            reply = QtWidgets.QMessageBox.question(
                window,
                dlcv_tr("确认删除"),
                dlcv_tr("是否确定要删除选中的 {count} 个标签？\n注意：这只会从标签列表中删除，不会影响已经标注的形状。"
                        ).format(count=len(selected_items)),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )

            if reply == QtWidgets.QMessageBox.Yes:
                for item in selected_items:
                    row = window.uniqLabelList.row(item)
                    window.uniqLabelList.takeItem(row)

                # 触发更新
                window.canvas.shapeMoved.emit()

        delete_action.triggered.connect(delete_uniq_label)
        menu.exec_(window.uniqLabelList.mapToGlobal(pos))

    # 为 uniqLabelList 设置右键菜单
    window.uniqLabelList.setContextMenuPolicy(Qt.CustomContextMenu)
    window.uniqLabelList.customContextMenuRequested.connect(
        show_uniq_label_menu)


def init_change_color_action(main_window):
    """初始化修改颜色 action（用于 uniqLabelList 右键菜单）"""
    action = utils.newAction(
        main_window,
        dlcv_tr("change color"),
        lambda: change_shape_color(main_window),
        None,
        "color",
        dlcv_tr("change the color of the selected polygon"),
        enabled=False,
    )
    main_window.actions.changeColor = action


def change_shape_color(main_window):
    """按 uniqLabelList 选中标签批量改色，并同步更新列表显示。"""
    selected_labels = {
        item.data(Qt.UserRole)
        for item in main_window.uniqLabelList.selectedItems()
    }
    if not selected_labels:
        return

    selected_shape_items = []
    for item in main_window.labelList:
        shape = item.shape()
        if shape and shape.label in selected_labels:
            selected_shape_items.append(item)
    if not selected_shape_items:
        return

    shape = selected_shape_items[0].shape()
    current_color = shape.fill_color

    from labelme.widgets import ColorDialog

    color_dialog = ColorDialog(main_window)
    new_color = color_dialog.getColor(
        value=current_color, title=dlcv_tr("选择颜色"), default=current_color)
    if new_color is None:
        return

    rgb = new_color.getRgb()[:3]

    # if main_window._config["shape_color"] != "manual":
    #     main_window._config["shape_color"] = "manual"
    # if main_window._config["label_colors"] is None:
    #     main_window._config["label_colors"] = {}

    changed_labels = set()
    for item in selected_shape_items:
        shape = item.shape()
        if not shape:
            continue
        changed_labels.add(shape.label)
        # main_window._config["label_colors"][shape.label] = rgb
        # 1) 更新 shape 颜色
        update_shape_color_with_rgb(shape, rgb)
        # 2) 更新 labelList 对应 shape item 颜色
        text = (
            shape.label
            if shape.group_id is None
            else "{} ({})".format(shape.label, shape.group_id)
        )
        item.setText(
            '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                html.escape(text), *shape.fill_color.getRgb()[:3]
            )
        )

    for i in range(main_window.uniqLabelList.count()):
        item = main_window.uniqLabelList.item(i)
        label = item.data(Qt.UserRole)
        if label in changed_labels:
            # 3) 更新 uniqLabelList item 颜色
            main_window.uniqLabelList.setItemLabel(item, label, rgb)

    main_window.setDirty()
    main_window.canvas.repaint()
    main_window.canvas.update()


def update_shape_color_with_rgb(shape, rgb):
    """使用指定 RGB 更新 shape 颜色"""
    r, g, b = rgb
    shape.line_color = QtGui.QColor(r, g, b)
    shape.vertex_fill_color = QtGui.QColor(r, g, b)
    shape.fill_color = QtGui.QColor(r, g, b, 128)
    shape.select_fill_color = QtGui.QColor(r, g, b, 155)
