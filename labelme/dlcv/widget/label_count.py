from PyQt5 import QtWidgets
from openpyxl.styles.builtins import total

from labelme.dlcv.shape import Shape
from labelme.dlcv import dlcv_tr
from labelme.utils.qt import newIcon
from collections import Counter
import os
import json


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
        """
        递归统计当前文件夹及所有子文件夹下json文件中的标签/文本标记数量，并在文本框中显示结果
        """
        # 假设parent有lastOpenDir属性
        parent = self.parent()
        dir_path = getattr(parent, "lastOpenDir", None)
        if not dir_path or not os.path.isdir(dir_path):
            self.label_count_text.setText(
                dlcv_tr("未检测到有效的图片文件夹，请先导入文件夹。")
            )
            return

        # 递归遍历文件夹下所有json文件
        json_files_count = 0
        label_counter = Counter()
        flag_counter = Counter()
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".json"):
                    json_path = os.path.join(root, file)
                    json_files_count += 1
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        shapes = data.get("shapes", [])
                        flags = data.get("flags", {})

                        # 统计标签
                        for shape in shapes:
                            label = shape.get("label", "")
                            if label:
                                label_counter[label] += 1

                        # 统计文本标记（只统计值为True的flag文本）
                        if isinstance(flags, dict):
                            for flag_name, flag_value in flags.items():
                                if flag_value is True:
                                    flag_counter[flag_name] += 1
                    except Exception as e:
                        continue

        if not label_counter and not flag_counter:
            if json_files_count == 0:
                self.label_count_text.setText(dlcv_tr("未找到任何JSON文件，请先进行标注。"))
            else:
                self.label_count_text.setText(
                    dlcv_tr("找到 {count} 个JSON文件，但未统计到任何标签。").format(
                        count=json_files_count
                    )
                )
        else:
            result = dlcv_tr("统计结果（共扫描 {count} 个JSON文件）：\n").format(
                count=json_files_count
            )
            if flag_counter:
                result += dlcv_tr("\n文本标记统计:\n")
                total_flags = sum(flag_counter.values())
                for flag, count in flag_counter.most_common():
                    result += f"{flag}: {count}\n"
                result += dlcv_tr("文本标记总数: {count}\n").format(count=total_flags)
            if label_counter:
                result += dlcv_tr("\n标签统计:\n")
                total_labels = sum(label_counter.values())
                # 使用most_common()方法按数量降序排列， 返回从高到低排序的元组列表
                for label, count in label_counter.most_common():
                    result += f"{label}: {count}\n"
                result += dlcv_tr("标签总数: {count}").format(count=total_labels)

            total = sum(label_counter.values()) + sum(flag_counter.values())
            result += dlcv_tr("\n\n总数: {count}").format(count=total)
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
