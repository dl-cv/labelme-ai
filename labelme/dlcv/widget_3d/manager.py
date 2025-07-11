import sys
from pathlib import Path

from labelme.dlcv.manager import ABCStrategy
from labelme.dlcv.store import STORE

# 支持的3D文件后缀
suffixes_3D = {'.tiff', '.tif', '.png'}


class ProjTypeEnum:
    D2 = '2D'
    D25 = '2.5D'
    D3 = '3D'


class NormalStrategy(ABCStrategy):

    def is_target(self, path: str) -> bool:
        return True  # 任意图都归为普通

    def get_json_path(self, path: str) -> str:
        return str(Path(path).with_suffix(".json"))

    def get_img_name_list(self, path: str) -> list[str]:
        return [Path(path).name]


class D25Strategy(ABCStrategy):

    def is_target(self, path: str) -> bool:
        suf = Path(path).suffix.lower()
        return suf in suffixes_3D and ("_C" in path or "_D" in path)

    def get_json_path(self, path: str) -> str:
        return str(Path(path).with_suffix(".json"))

    def get_img_name_list(self, path: str) -> list[str]:
        return [Path(path).name]


# class ProjManager:
#     """
#     3D 数据管理类
#     通过灰度图和深度图的文件路径，管理3D数据的路径
#     """
#
#     def is_3d_data(self, img_path: str):
#         suffix = Path(img_path).suffix
#
#         gray_img_path = self.get_gray_img_path(img_path)
#         depth_img_path = self.get_depth_img_path(img_path)
#
#         if gray_img_path.endswith(f'_G{suffix}') and depth_img_path.endswith(f'_H{suffix}') and suffix in suffixes_3D:
#             return True
#         else:
#             return False
#
#     def get_img_name_list(self, img_path: str) -> list[str]:
#         import os
#         gray_img_path = self.get_gray_img_path(img_path)
#         depth_img_path = self.get_depth_img_path(img_path)
#
#         gray_img_name = os.path.basename(gray_img_path)
#         depth_img_name = os.path.basename(depth_img_path)
#
#         return [gray_img_name, depth_img_name, gray_img_name]
#
#     def get_json_path(self, img_path: str) -> str:
#         if not STORE.main_window.is_3d or not self.is_3d_data(img_path):
#             return str(Path(img_path).with_suffix('.json'))
#
#         suffix = Path(img_path).suffix
#         gray_img_path = self.get_gray_img_path(img_path)
#         return gray_img_path.replace(f'_G{suffix}', '.json')


def get_gray_path(path: str) -> str:
    suf = Path(path).suffix
    if f'_G{suf}' in path and suf in suffixes_3D:  # 灰度图
        return path
    elif f'_H{suf}' in path and suf in suffixes_3D:  # 深度图
        return path.replace(f'_H{suf}', f'_G{suf}')
    else:
        return path  # 非3D图


def get_depth_path(path: str) -> str:
    suf = Path(path).suffix
    if f'_H{suf}' in path and suf in suffixes_3D:  # 深度图
        return path
    elif f'_G{suf}' in path and suf in suffixes_3D:  # 灰度图
        return path.replace(f'_G{suf}', f'_H{suf}')
    else:
        return path  # 非3D图


class D3Strategy(ABCStrategy):
    """3D图像处理策略 (_G.suffix + _H.suffix)"""

    def is_target(self, path: str) -> bool:
        suffix = Path(path).suffix

        gray_img_path = get_gray_path(path)
        depth_img_path = get_depth_path(path)

        if gray_img_path.endswith(f'_G{suffix}') and depth_img_path.endswith(
                f'_H{suffix}') and suffix in suffixes_3D:
            return True
        else:
            return False

    def get_json_path(self, img_path: str) -> str:
        suffix = Path(img_path).suffix
        gray_img_path = get_gray_path(img_path)
        return gray_img_path.replace(f'_G{suffix}', '.json')

    def get_img_name_list(self, img_path: str) -> list[str]:
        """返回[灰度图名,深度图名,灰度图名]"""
        gray = get_gray_path(img_path)
        depth = get_depth_path(img_path)
        return [
            Path(gray).name,
            Path(depth).name,
            Path(gray).name,
        ]


class ProjManager:
    """项目管理类"""
    _strategy_map = {
        ProjTypeEnum.D2: NormalStrategy(),
        ProjTypeEnum.D25: D25Strategy(),
        ProjTypeEnum.D3: D3Strategy(),
    }

    @property
    def proj_type(self) -> str:
        """获取当前项目类型"""
        type_str = STORE.main_window.proj_type_param.value()
        return type_str

    @property
    def strategy(self) -> ABCStrategy:
        """获取当前策略"""
        return self._strategy_map[self.proj_type]

    def is_target_data(self, img_path: str) -> bool:
        """判断是否为目标类型数据"""
        return self.strategy.is_target(img_path)

    def get_json_path(self, img_path: str) -> str:
        """获取json标注文件路径"""
        if not self.is_target_data(img_path):
            return str(Path(img_path).with_suffix('.json'))

        raw_json_path = self.strategy.get_json_path(img_path)
        assert raw_json_path.endswith('.json')
        return raw_json_path

    def get_img_name_list(self, img_path: str) -> list[str]:
        return self.strategy.get_img_name_list(img_path)

    def get_gray_img_path(self, img_path: str) -> str:
        return get_gray_path(img_path)

    def get_depth_img_path(self, img_path: str) -> str | None:
        return get_depth_path(img_path)


class TestProjManager(ProjManager):

    def __init__(self):
        self._proj_type = ProjTypeEnum.D2

    @property
    def proj_type(self) -> str:
        return self._proj_type


if "pytest" in sys.modules:
    __manager_test__ = TestProjManager()


def test_D2_with_normal_data():
    # 常规项目 - 2D数据
    __manager_test__._proj_type = ProjTypeEnum.D2
    test_normal_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.jpg"
    test_normal_json_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.json"

    gray_path_1 = __manager_test__.get_gray_img_path(test_normal_path)
    depth_path_1 = __manager_test__.get_depth_img_path(test_normal_path)
    json_path_1 = __manager_test__.get_json_path(test_normal_path)

    assert __manager_test__.is_target_data(test_normal_path)
    assert gray_path_1 == test_normal_path
    assert depth_path_1 == test_normal_path
    assert json_path_1 == test_normal_json_path


def test_D2_with_D3_data():
    __manager_test__._proj_type = ProjTypeEnum.D2

    # --------- 灰度图测试 ---------
    test_gray_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_G.tiff"
    test_json_path_1 = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_G.json"

    depth_path = __manager_test__.get_depth_img_path(test_gray_path)
    json_path_1 = __manager_test__.get_json_path(test_gray_path)

    assert json_path_1 == test_json_path_1

    # --------- 深度图测试 ---------
    test_depth_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_H.tiff"
    test_json_path_2 = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_H.json"

    gray_path = __manager_test__.get_gray_img_path(test_depth_path)
    json_path_2 = __manager_test__.get_json_path(test_depth_path)

    assert json_path_2 == test_json_path_2

    assert __manager_test__.is_target_data(test_gray_path)
    assert gray_path == test_gray_path
    assert depth_path == test_depth_path


def test_D3_with_normal_data():
    # 3D 项目 - 2D数据
    __manager_test__._proj_type = ProjTypeEnum.D3
    test_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.jpg"
    test_json_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.json"

    gray_path_1 = __manager_test__.get_gray_img_path(test_path)
    depth_path_1 = __manager_test__.get_depth_img_path(test_path)
    json_path_1 = __manager_test__.get_json_path(test_path)

    assert not __manager_test__.is_target_data(test_path)
    assert gray_path_1 == test_path
    assert depth_path_1 == test_path
    assert json_path_1 == test_json_path


def test_D3_with_D3_data():
    # 3D 项目 - 3D数据
    __manager_test__._proj_type = ProjTypeEnum.D3
    test_gray_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_G.tiff"
    test_depth_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_H.tiff"
    test_json_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1.json"

    gray_path_2 = __manager_test__.get_gray_img_path(test_depth_path)
    depth_path_2 = __manager_test__.get_depth_img_path(test_gray_path)
    json_path_2 = __manager_test__.get_json_path(test_gray_path)

    assert __manager_test__.is_target_data(test_gray_path)
    assert gray_path_2 == test_gray_path
    assert depth_path_2 == test_depth_path
    assert json_path_2 == test_json_path
