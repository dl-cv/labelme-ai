import os
from dataclasses import dataclass, field
from typing import Dict, Any

import yaml
from qtpy import QtWidgets, QtCore

from labelme.dlcv import tr

BASE_DIR = "Y:\cjj\labelme-ai-dataset"
DATASET_TYPES = ["分类", "检测", "分割"]


@dataclass
class DatasetConfig:
    dataset_root_path: str
    # 使用字典存储其他可能的配置项
    extra_configs: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DatasetConfig':
        """从字典创建配置对象"""
        dataset_root_path = data.pop('dataset_root_path')
        return cls(dataset_root_path=dataset_root_path, extra_configs=data)

    def to_dict(self) -> Dict[str, Any]:
        """将配置对象转换为字典"""
        return {
            'dataset_root_path': self.dataset_root_path,
            **self.extra_configs
        }

    def save_to_yaml(self, yaml_path: str):
        """保存配置到yaml文件"""
        os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True)


class DatasetItem(QtWidgets.QListWidgetItem):

    def __init__(self, config: DatasetConfig):
        super().__init__(config.dataset_root_path)
        self.setData(QtCore.Qt.UserRole, config)

    def get_config(self):
        return self.data(QtCore.Qt.UserRole)


class DatasetPathManagerDock(QtWidgets.QDockWidget):
    """数据集路径管理器
    用于管理不同类型(分类/检测/分割)的数据集路径，每个数据集信息用单独的yaml文件配置
    """
    # 修改信号，发送DatasetItem
    item_clicked = QtCore.Signal(DatasetItem)

    def __init__(self, parent=None):
        super().__init__(tr("常用数据集"), parent)
        self.setup_ui()
        self.load_datasets()

    def setup_ui(self):
        # 创建主控件和布局
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建顶部工具栏
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        # 添加按钮
        self.add_button = QtWidgets.QPushButton(tr("添加常用数据集"))
        self.add_button.clicked.connect(self.add_dataset)
        toolbar.addWidget(self.add_button)

        # 创建搜索框
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText(tr("搜索..."))
        toolbar.addWidget(self.search_box)

        layout.addLayout(toolbar)

        # 创建标签页控件
        self.tab_widget = QtWidgets.QTabWidget()

        # 为每种数据集类型创建列表
        self.dataset_lists = {}
        for dataset_type in DATASET_TYPES:
            list_widget = QtWidgets.QListWidget()
            # 连接点击信号
            list_widget.itemClicked.connect(self.on_item_clicked)
            self.dataset_lists[dataset_type] = list_widget
            self.tab_widget.addTab(list_widget, tr(dataset_type))

        layout.addWidget(self.tab_widget)
        self.setWidget(main_widget)

        # 连接信号
        self.search_box.textChanged.connect(self.filter_items)

    def load_datasets(self):
        """加载数据集配置"""
        if os.path.exists(BASE_DIR):
            for dataset_type in DATASET_TYPES:
                type_dir = os.path.join(BASE_DIR, dataset_type)
                if os.path.exists(type_dir):
                    self.load_yaml_files(dataset_type, type_dir)

    def load_yaml_files(self, dataset_type, type_dir):
        """加载指定类型目录下的所有yaml文件"""
        try:
            # 获取目录下所有yaml文件
            yaml_files = [
                f for f in os.listdir(type_dir)
                if f.endswith(('.yaml', '.yml'))
            ]

            for yaml_file in yaml_files:
                file_path = os.path.join(type_dir, yaml_file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        yaml_data = yaml.safe_load(f)
                        # 添加到列表中
                        self.add_dataset_config(dataset_type, yaml_file,
                                                yaml_data)
                except Exception as e:
                    print(f"加载yaml文件失败 {yaml_file}: {e}")
        except Exception as e:
            print(f"读取目录失败 {type_dir}: {e}")

    def add_dataset_config(self, dataset_type, yaml_file, yaml_data):
        """添加数据集配置到列表中"""
        if dataset_type not in self.dataset_lists:
            return

        list_widget = self.dataset_lists[dataset_type]

        # 将yaml数据转换为DatasetConfig对象
        if isinstance(yaml_data, dict):
            try:
                config = DatasetConfig.from_dict(yaml_data.copy())
                # 创建列表项，显示数据集路径
                item = DatasetItem(config)
                list_widget.addItem(item)
            except KeyError as e:
                print(f"无效的配置文件 {yaml_file}: 缺少必需字段 {e}")

    def filter_items(self, text):
        """根据搜索文本过滤列表项"""
        for list_widget in self.dataset_lists.values():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                # 在文件名和yaml内容中搜索
                config = item.data(QtCore.Qt.UserRole)
                if isinstance(config, DatasetConfig):
                    yaml_text = yaml.dump(config.to_dict(), allow_unicode=True)
                else:
                    yaml_text = ""
                if (text.lower() in item.text().lower()
                        or text.lower() in yaml_text.lower()):
                    item.setHidden(False)
                else:
                    item.setHidden(True)

    def add_dataset(self):
        """添加新的数据集配置"""
        # 获取当前选中的数据集类型
        current_type = DATASET_TYPES[self.tab_widget.currentIndex()]

        # 选择数据集文件夹
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, tr("选择数据集文件夹"), "", QtWidgets.QFileDialog.ShowDirsOnly)

        if folder_path:
            # 创建配置对象
            config = DatasetConfig(dataset_root_path=folder_path)

            # 获取默认文件名（文件夹名）
            default_name = os.path.basename(folder_path)

            # 让用户输入yaml文件名
            yaml_name, ok = QtWidgets.QInputDialog.getText(
                self, tr("输入配置文件名"), tr("请输入配置文件名（不需要.yaml后缀）："),
                QtWidgets.QLineEdit.Normal, default_name)

            if ok and yaml_name:
                # 添加.yaml后缀
                yaml_file = f"{yaml_name}.yaml"
                yaml_path = os.path.join(BASE_DIR, current_type, yaml_file)

                os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
                config.save_to_yaml(yaml_path)

                # 添加到列表中
                self.add_dataset_config(current_type, yaml_file,
                                        config.to_dict())

    def on_item_clicked(self, item):
        """处理列表项点击事件"""
        if isinstance(item, DatasetItem):
            self.item_clicked.emit(item)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    widget = DatasetPathManagerDock()
    widget.resize(800, 600)
    widget.show()
    sys.exit(app.exec_())
