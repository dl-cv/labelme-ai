from pathlib import Path
import os
from abc import ABC, abstractmethod

from labelme.dlcv.store import STORE
from labelme.dlcv.widget_25d_3d.assign_json import assign_json
from labelme.dlcv.app import ProjEnum


class ProjManagerBase(ABC):
    @abstractmethod
    def get_json_path(self, img_path: str) -> str:
        pass

    def get_img_name_list(self, path: str) -> list[str]:
        """
        获取图片名列表
        
        Args:
            path: 对于2D/3D模式是图片路径，对于2.5D模式是JSON路径
        
        Returns:
            图片名列表
        """
        return []


class ProjNormalManager(ProjManagerBase):
    """2D模式管理器"""
    
    def get_json_path(self, img_path: str) -> str:
        return str(Path(img_path).with_suffix('.json'))


class Proj3DManager(ProjManagerBase):
    """3D模式管理器"""
    
    suffixes_3D = ['.tiff', '.tif', '.png']
    
    def get_gray_img_path(self, img_path: str) -> str:
        suffix = Path(img_path).suffix
        if img_path.endswith(f'_H{suffix}'):
            return img_path.replace(f'_H{suffix}', f'_G{suffix}')
        return img_path
    
    def get_depth_img_path(self, img_path: str) -> str:
        suffix = Path(img_path).suffix
        if img_path.endswith(f'_G{suffix}'):
            return img_path.replace(f'_G{suffix}', f'_H{suffix}')
        return img_path
    
    def is_3d_data(self, img_path: str) -> bool:
        suffix = Path(img_path).suffix
        gray_img_path = self.get_gray_img_path(img_path)
        depth_img_path = self.get_depth_img_path(img_path)
        return (gray_img_path.endswith(f'_G{suffix}') and 
                depth_img_path.endswith(f'_H{suffix}') and 
                suffix in self.suffixes_3D)
    
    def get_json_path(self, img_path: str) -> str:
        if not self.is_3d_data(img_path):
            return str(Path(img_path).with_suffix('.json'))
        suffix = Path(img_path).suffix
        gray_img_path = self.get_gray_img_path(img_path)
        return gray_img_path.replace(f'_G{suffix}', '.json')
    
    def get_img_name_list(self, img_path: str) -> list[str]:
        """获取3D数据的图片名列表（参数是图片路径）"""
        gray_img_path = self.get_gray_img_path(img_path)
        depth_img_path = self.get_depth_img_path(img_path)
        gray_img_name = os.path.basename(gray_img_path)
        depth_img_name = os.path.basename(depth_img_path)
        return [gray_img_name, depth_img_name, gray_img_name]


class Proj2_5DManager(ProjManagerBase):
    """2.5D模式管理器"""
    
    def __init__(self):
        self._file_to_json = {}
    
    def assign_json_files(self, root_path: str) -> dict:
        """分配JSON文件"""
        if not root_path or not os.path.exists(root_path):
            return {}
        try:
            self._file_to_json = assign_json(root_path)
            return self._file_to_json
        except Exception:
            return {}
    
    def get_json_path(self, img_path: str) -> str:
        if not self._file_to_json:
            if STORE.main_window and hasattr(STORE.main_window, 'lastOpenDir'):
                root_path = STORE.main_window.lastOpenDir
                if root_path and os.path.exists(root_path):
                    self.assign_json_files(root_path)
        
        img_name = os.path.basename(img_path)
        if img_name in self._file_to_json:
            json_name = self._file_to_json[img_name]
            return os.path.join(os.path.dirname(img_path), json_name)
        return str(Path(img_path).with_suffix('.json'))
    
    def get_img_name_list(self, json_path: str) -> list[str]:
        """获取使用指定JSON的所有图片名列表（参数是JSON路径）"""
        json_name = os.path.basename(json_path)
        return [img_name for img_name, json_file in self._file_to_json.items() 
                if json_file == json_name]

    def clear(self):
        """清空映射"""
        self._file_to_json = {}
    
    @property
    def file_to_json(self) -> dict:
        return self._file_to_json.copy()
    
    @file_to_json.setter
    def file_to_json(self, value: dict):
        self._file_to_json = value.copy() if value else {}

# 项目管理器
class ProjManager:
    """
    策略上下文：根据 STORE 的状态自动切换对应的 Manager
    """
    
    def __init__(self):
        """初始化项目管理器，创建所有模式的管理器"""
        # 预先初始化所有策略，保留 2.5D 的状态
        self._strategies = {
            ProjEnum.NORMAL: ProjNormalManager(),
            ProjEnum.O2_5D: Proj2_5DManager(),
            ProjEnum.O3D: Proj3DManager()
        }
    
    @property
    def current_manager(self) -> ProjManagerBase:
        """
        动态获取当前的管理器实例
        """
        # 从 STORE 获取当前类型
        proj_type = ProjEnum.NORMAL
        if STORE.main_window:
            proj_type = STORE.main_window.parameter.child("proj_setting", "proj_type").value()
        
        # 返回对应的管理器，默认为 NORMAL
        return self._strategies.get(proj_type, self._strategies[ProjEnum.NORMAL])
    
    # --- 核心：通用方法直接委托，不再写 if/else ---
    
    def get_json_path(self, img_path: str) -> str:
        """获取图片对应的JSON文件路径（多态委托）"""
        return self.current_manager.get_json_path(img_path)
    
    def get_img_name_list(self, path: str) -> list[str]:
        """
        获取图片名列表（多态委托）
        
        Args:
            path: 对于2D/3D模式是图片路径，对于2.5D模式是JSON路径
        
        Returns:
            图片名列表
        """
        return self.current_manager.get_img_name_list(path)
    
    # --- 显式暴露特有属性 ---
    @property
    def norm_manager(self) -> ProjNormalManager:
        """2D模式管理器"""
        return self._strategies[ProjEnum.NORMAL]
    
    @property
    def o3d_manager(self) -> Proj3DManager:
        """3D模式管理器"""
        return self._strategies[ProjEnum.O3D]
    
    @property
    def o2_5d_manager(self) -> Proj2_5DManager:
        """2.5D模式管理器"""
        return self._strategies[ProjEnum.O2_5D]
    
    @property
    def is_3d(self) -> bool:
        """是否3D模式"""
        return isinstance(self.current_manager, Proj3DManager)
    
    @property
    def is_2_5d(self) -> bool:
        """是否2.5D模式"""
        return isinstance(self.current_manager, Proj2_5DManager)

    # region
    # ============3D模式方法================
    def get_gray_img_path(self, img_path: str) -> str:
        """获取灰度图路径（只有3D Manager有这个方法）"""
        return self.o3d_manager.get_gray_img_path(img_path)
    
    def get_depth_img_path(self, img_path: str) -> str:
        """获取深度图路径（只有3D Manager有这个方法）"""
        return self.o3d_manager.get_depth_img_path(img_path)
    
    def is_3d_data(self, img_path: str) -> bool:
        """判断是否为3D数据（只有3D Manager有这个方法）"""
        return self.o3d_manager.is_3d_data(img_path)
    # endregion
    
    # region
    # ============2.5D模式方法================
    def assign_json_files(self, root_path: str) -> dict:
        """分配JSON文件"""
        return self.o2_5d_manager.assign_json_files(root_path)
    
    def clear(self):
        """清空映射"""
        self.o2_5d_manager.clear()
    
    @property
    def file_to_json(self) -> dict:
        """获取文件到JSON的映射"""
        if self.is_2_5d:
            return self.o2_5d_manager.file_to_json
        return {}
    
    @property
    def _file_to_json(self) -> dict:
        """内部属性访问"""
        return self.o2_5d_manager._file_to_json
    # endregion