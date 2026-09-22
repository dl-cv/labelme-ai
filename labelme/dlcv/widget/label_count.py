from PyQt5 import QtWidgets
from openpyxl.styles.builtins import total

from labelme.dlcv.shape import Shape
from labelme.dlcv import dlcv_tr
from labelme.utils.qt import newIcon
from collections import Counter
import os
import json
from pathlib import Path

try:
    from dlcv_core.image_annotations import collect_annotation_paths, load_annotation
except ModuleNotFoundError as exc:
    if exc.name not in {"dlcv_core", "dlcv_core.image_annotations"}:
        raise
    collect_annotation_paths = None
    load_annotation = None


class LabelCountDock(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__(dlcv_tr("标签/文本标记数量统计"), parent)
        self.setObjectName("label_count_dock")
        self.setWindowIcon(newIcon("label_count"))

        # 创建主widget和布局
        main_widget = QtWidgets.QWidget(self)
        main_widget.setObjectName("labelCountPanel")
        layout = QtWidgets.QVBoxLayout(main_widget)
        main_widget.setLayout(layout)

        # 标签统计显示区域
        self.label_count_text = QtWidgets.QTextEdit(main_widget)
        self.label_count_text.setObjectName("labelCountText")
        self.label_count_text.setReadOnly(True)
        layout.addWidget(self.label_count_text)

        # 添加统计按钮
        self.label_count_btn = QtWidgets.QPushButton(
            dlcv_tr("统计当前文件夹标签/文本标记总数"), main_widget
        )
        self.label_count_btn.setObjectName("labelCountBtn")
        layout.addWidget(self.label_count_btn)

        # 去除控件间间距
        # 更贴近截图的“卡片内边距/间距”
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.setWidget(main_widget)

        # 按钮点击事件
        self.label_count_btn.clicked.connect(self.count_labels_in_dir)

    # 统计当前文件夹内的标签/标记数量
    def count_labels_in_dir(self):
        """递归统计图片内嵌优先的标注，同一份标注只计数一次。"""
        parent = self.parent()
        dir_path = getattr(parent, "lastOpenDir", None)
        if not dir_path or not os.path.isdir(dir_path):
            self.label_count_text.setText(
                dlcv_tr("未检测到有效的图片文件夹，请先导入文件夹。")
            )
            return

        try:
            annotation_paths = (
                collect_annotation_paths(dir_path)
                if collect_annotation_paths is not None
                else sorted(Path(dir_path).rglob("*.json"))
            )
        except Exception as exc:
            self.label_count_text.setText(
                dlcv_tr("读取文件夹标注失败：{error}").format(error=exc)
            )
            return

        label_counter = Counter()
        flag_counter = Counter()
        failed_count = 0
        for path in annotation_paths:
            try:
                data = (
                    load_annotation(path)
                    if load_annotation is not None
                    else json.loads(path.read_text(encoding="utf-8-sig"))
                )
                if not isinstance(data, dict):
                    continue
                for shape in data.get("shapes", []):
                    label = shape.get("label", "")
                    if label:
                        label_counter[label] += 1
                flags = data.get("flags", {})
                if isinstance(flags, dict):
                    for flag_name, flag_value in flags.items():
                        if flag_value is True:
                            flag_counter[flag_name] += 1
            except Exception:
                failed_count += 1

        if not annotation_paths:
            result = dlcv_tr("未找到任何标注，请先进行标注。")
        elif not label_counter and not flag_counter:
            result = dlcv_tr("找到 {count} 份标注，但未统计到任何标签或文本标记。").format(
                count=len(annotation_paths)
            )
        else:
            result = dlcv_tr("统计结果（共扫描 {count} 份标注）：\n").format(
                count=len(annotation_paths)
            )
            if flag_counter:
                result += dlcv_tr("\n文本标记统计:\n")
                for flag, count in flag_counter.most_common():
                    result += f"{flag}: {count}\n"
                result += dlcv_tr("文本标记总数: {count}\n").format(
                    count=sum(flag_counter.values())
                )
            if label_counter:
                result += dlcv_tr("\n标签统计:\n")
                for label, count in label_counter.most_common():
                    result += f"{label}: {count}\n"
                result += dlcv_tr("标签总数: {count}").format(
                    count=sum(label_counter.values())
                )
            result += dlcv_tr("\n\n总数: {count}").format(
                count=sum(label_counter.values()) + sum(flag_counter.values())
            )
        if failed_count:
            result += dlcv_tr("\n读取失败: {count} 份标注").format(count=failed_count)
        self.label_count_text.setText(result)

    # 统计当前文件的标签/标记数量; 在画布的save函数中调用
    def count_labels_in_file(self, shapes: list[Shape], flags: dict):
        label_counter = Counter()
        flag_counter = Counter()

        # 统计标签
        for shape in shapes:
            label = shape.label
            if label:
                label_counter[label] += 1

        # 统计文本标记（只统计值为True的flag文本）
        if isinstance(flags, dict):
            for flag_name, flag_value in flags.items():
                if flag_value is True:
                    flag_counter[flag_name] += 1

        result = dlcv_tr("当前文件统计结果：\n")
        if flag_counter:
            result += dlcv_tr("\n文本标记统计:\n")
            total_flags = sum(flag_counter.values())
            for flag, count in flag_counter.most_common():
                result += f"{flag}: {count}\n"
            result += dlcv_tr("文本标记总数: {count}\n").format(count=total_flags)
        if label_counter:
            result += dlcv_tr("\n标签统计:\n")
            total_labels = sum(label_counter.values())
            for label, count in label_counter.most_common():
                result += f"{label}: {count}\n"
            result += dlcv_tr("标签总数: {count}").format(count=total_labels) + "\n"

        total = sum(label_counter.values()) + sum(flag_counter.values())
        if total > 0:
            result += dlcv_tr("\n总数: {count}").format(count=total)
        else:
            result += dlcv_tr("\n当前文件暂无标注数据")
        self.label_count_text.setText(result)

        return result
