from PyQt5 import QtWidgets
from openpyxl.styles.builtins import total

from labelme.dlcv import tr
from labelme.utils.qt import newIcon
from collections import Counter
import os
import json

class LabelCountDock(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__(tr("标签/文本标记数量统计"), parent)
        self.setObjectName("label_count_dock")
        self.setWindowIcon(newIcon("label_count"))

        # 创建主widget和布局
        main_widget = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(main_widget)
        main_widget.setLayout(layout)

        # 标签统计显示区域
        self.label_count_text = QtWidgets.QTextEdit(main_widget)
        self.label_count_text.setReadOnly(True)
        layout.addWidget(self.label_count_text)

        # 添加统计按钮
        self.label_count_btn = QtWidgets.QPushButton("统计当前文件夹标签/文本标记总数", main_widget)
        layout.addWidget(self.label_count_btn)

        # 去除控件间间距
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setWidget(main_widget)

        # 按钮点击事件
        self.label_count_btn.clicked.connect(self.count_labels_in_dir)

    def count_labels_in_dir(self):
        """
        递归统计当前文件夹及所有子文件夹下json文件中的标签/文本标记数量，并在文本框中显示结果
        """
        # 假设parent有lastOpenDir属性
        parent = self.parent()
        dir_path = getattr(parent, "lastOpenDir", None)
        if not dir_path or not os.path.isdir(dir_path):
            self.label_count_text.setText("未检测到有效的图片文件夹，请先导入文件夹。")
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
                self.label_count_text.setText("未找到任何JSON文件，请先进行标注。")
            else:
                self.label_count_text.setText(f"找到 {json_files_count} 个JSON文件，但未统计到任何标签。")
        else:
            result = f"统计结果（共扫描 {json_files_count} 个JSON文件）：\n"
            if flag_counter:
                result += "\n文本标记统计:\n"
                total_flags = sum(flag_counter.values())
                for flag, count in flag_counter.most_common():
                    result += f"{flag}: {count}\n"
                result += f"文本标记总数: {total_flags}\n"
            if label_counter:
                result += "\n标签统计:\n"
                total_labels = sum(label_counter.values())
                # 使用most_common()方法按数量降序排列， 返回从高到低排序的元组列表
                for label, count in label_counter.most_common():
                    result += f"{label}: {count}\n"
                result += f"标签总数: {total_labels}"

            total = sum(label_counter.values()) + sum(flag_counter.values())
            result += f'\n\n总数: {total}'
            self.label_count_text.setText(result)
