from pathlib import Path

from labelme.dlcv.store import STORE

suffixes_3D = ['.tiff', '.tif', '.png']


class ProjManager:
    """
    3D 数据管理类
    通过灰度图和深度图的文件路径，管理3D数据的路径
    """

    def get_gray_img_path(self, img_path: str):
        suffix = Path(img_path).suffix
        if img_path.endswith(f'_H{suffix}'):
            return img_path.replace(f'_H{suffix}', f'_G{suffix}')
        else:
            return img_path

    def get_depth_img_path(self, img_path: str):
        suffix = Path(img_path).suffix

        if img_path.endswith(f'_G{suffix}'):
            return img_path.replace(f'_G{suffix}', f'_H{suffix}')
        else:
            return img_path

    @property
    def __is_3d(self):
        try:
            return STORE.main_window.is_3d
        except:
            return self._is_3d  # 测试用

    def is_3d_data(self, img_path: str):
        suffix = Path(img_path).suffix

        gray_img_path = self.get_gray_img_path(img_path)
        depth_img_path = self.get_depth_img_path(img_path)

        if gray_img_path.endswith(f'_G{suffix}') and depth_img_path.endswith(
                f'_H{suffix}') and suffix in suffixes_3D:
            return True
        else:
            return False

    def get_img_name_list(self, img_path: str) -> list[str]:
        import os
        gray_img_path = self.get_gray_img_path(img_path)
        depth_img_path = self.get_depth_img_path(img_path)

        gray_img_name = os.path.basename(gray_img_path)
        depth_img_name = os.path.basename(depth_img_path)

        return [gray_img_name, depth_img_name, gray_img_name]

    def get_json_path(self, img_path: str) -> str:
        if not self.__is_3d or not self.is_3d_data(img_path):
            return str(Path(img_path).with_suffix('.json'))

        suffix = Path(img_path).suffix
        gray_img_path = self.get_gray_img_path(img_path)
        return gray_img_path.replace(f'_G{suffix}', '.json')


def test_manager():
    manager_test = ProjManager()

    # 常规项目 - 常规数据
    manager_test._is_3d = False
    test_normal_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.jpg"
    test_normal_json_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.json"

    gray_path_1 = manager_test.get_gray_img_path(test_normal_path)
    depth_path_1 = manager_test.get_depth_img_path(test_normal_path)
    json_path_1 = manager_test.get_json_path(test_normal_path)

    assert not manager_test.is_3d_data(test_normal_path)
    assert gray_path_1 == test_normal_path
    assert depth_path_1 == test_normal_path
    assert json_path_1 == test_normal_json_path

    # 3D 项目 - 常规数据
    manager_test._is_3d = True
    test_normal_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.jpg"
    test_normal_json_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\145053828_e0e748717c_b.json"

    gray_path_1 = manager_test.get_gray_img_path(test_normal_path)
    depth_path_1 = manager_test.get_depth_img_path(test_normal_path)
    json_path_1 = manager_test.get_json_path(test_normal_path)

    assert not manager_test.is_3d_data(test_normal_path)
    assert gray_path_1 == test_normal_path
    assert depth_path_1 == test_normal_path
    assert json_path_1 == test_normal_json_path

    # 3D 项目 - 3D数据
    manager_test._is_3d = True
    test_gray_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_G.tiff"
    test_depth_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1_H.tiff"
    test_json_path = r"C:\Users\Admin\Desktop\work_space\labelme\tests\0021_18-57-01_28057__1.json"

    gray_path_2 = manager_test.get_gray_img_path(test_depth_path)
    depth_path_2 = manager_test.get_depth_img_path(test_gray_path)
    json_path_2 = manager_test.get_json_path(test_gray_path)

    assert manager_test.is_3d_data(test_gray_path)
    assert gray_path_2 == test_gray_path
    assert depth_path_2 == test_depth_path
    assert json_path_2 == test_json_path
