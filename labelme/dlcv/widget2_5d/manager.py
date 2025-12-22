import os
from pathlib import Path

from labelme.dlcv.store import STORE
from labelme.dlcv.widget2_5d.assign_json import assign_json

class Proj2_5DManager:
    """
    2.5D 数据管理类
    管理2.5D模式下多个图片共享一个JSON文件的逻辑
    """

    def __init__(self):
        """初始化2.5D管理器"""
        self._file_to_json = {}  # 文件名到JSON文件名的映射

    def assign_json_files(self, root_path: str) -> dict:
        """
        分配JSON文件，返回文件名到JSON文件名的映射
        
        Args:
            root_path: 根目录路径
            
        Returns:
            dict: 文件名到JSON文件名的映射
        """
        if not root_path or not os.path.exists(root_path):
            return {}
        
        try:
            self._file_to_json = assign_json(root_path)
            return self._file_to_json
        except Exception as e:
            return {}

    def get_json_path(self, img_path: str) -> str:
        """
        获取图片对应的JSON文件路径
        
        Args:
            img_path: 图片文件路径
            
        Returns:
            str: JSON文件路径
        """
        if not self._file_to_json:
            # 如果映射为空，尝试自动分配
            if STORE.main_window and hasattr(STORE.main_window, 'lastOpenDir'):
                root_path = STORE.main_window.lastOpenDir
                if root_path and os.path.exists(root_path):
                    self.assign_json_files(root_path)
        
        img_name = os.path.basename(img_path)
        if img_name in self._file_to_json:
            json_name = self._file_to_json[img_name]
            img_dir = os.path.dirname(img_path)
            return os.path.join(img_dir, json_name)
        
        # 如果找不到映射，使用默认逻辑
        return str(Path(img_path).with_suffix('.json'))

    def get_image_name_list(self, json_path: str) -> list[str]:
        """
        获取使用指定JSON文件的所有图片名列表
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            list[str]: 图片名列表
        """
        json_name = os.path.basename(json_path)
        img_name_list = [
            img_name 
            for img_name, json_file in self._file_to_json.items()
            if json_file == json_name
        ]
        return img_name_list

    def is_image_in_json(self, img_path: str, json_path: str) -> bool:
        """
        检查图片是否在JSON文件的imagePath列表中
        
        Args:
            img_path: 图片文件路径
            json_path: JSON文件路径
            
        Returns:
            bool: 如果图片在JSON的imagePath列表中返回True
        """
        import json
        img_name = os.path.basename(img_path)
        
        if not os.path.exists(json_path):
            return False
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                image_path = json_data.get("imagePath", [])
                
                # 如果imagePath是列表，检查图片名是否在列表中
                if isinstance(image_path, list):
                    return img_name in image_path
                else:
                    # 如果是字符串，使用原有逻辑
                    return True
        except Exception:
            return False

    def update_image_path_list(self, json_path: str) -> list[str]:
        """
        更新JSON文件的imagePath列表，返回所有使用该JSON的图片名列表
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            list[str]: 图片名列表
        """
        return self.get_image_name_list(json_path)

    def clear(self):
        """清空映射"""
        self._file_to_json = {}

    @property
    def file_to_json(self) -> dict:
        """获取文件名到JSON文件名的映射"""
        return self._file_to_json.copy()

    @file_to_json.setter
    def file_to_json(self, value: dict):
        """设置文件名到JSON文件名的映射"""
        self._file_to_json = value.copy() if value else {}

