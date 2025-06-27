import numpy as np
import cv2
import open3d as o3d
from labelme.dlcv.utils_func import normalize_16b_gray_to_uint8


def check_img(img: np.ndarray):
    # 输入验证
    if not isinstance(img, np.ndarray):
        raise ValueError("输入必须是numpy数组")

    if img.size == 0:
        raise ValueError("输入数组不能为空")

    if img.ndim not in (2, 3, 4):
        raise ValueError("输入图像必须是2D（灰度）或3D（BGR）或4D（BGRD）数组")

    # 检查数据类型
    if img.dtype not in (np.uint8, np.uint16, np.float32, np.float64):
        raise ValueError(f"不支持的数据类型: {img.dtype}，支持的类型: uint8, uint16, float32, float64")

    # 检查无效值
    if np.any(np.isnan(img)) or np.any(np.isinf(img)):
        raise ValueError("输入图像包含无效值（NaN或Inf）")


def img2pcd(bgr_img: np.ndarray, depth_img: np.ndarray, scale: float = 0.2) -> o3d.geometry:
    """
    将BGR图像和深度图像转换为点云

    :param bgr_img: BGR图像
    :param depth_img: 深度图像
    :param scale: 点云缩放因子
    :return: 点云
    """

    # # Generate some neat n times 3 matrix using a variant of sync function
    # x = np.linspace(-3, 3, 401)
    # mesh_x, mesh_y = np.meshgrid(x, x)
    # z = np.sinc((np.power(mesh_x, 2) + np.power(mesh_y, 2)))
    # z_norm = (z - z.min()) / (z.max() - z.min())
    # xyz = np.zeros((np.size(mesh_x), 3))
    # xyz[:, 0] = np.reshape(mesh_x, -1)
    # xyz[:, 1] = np.reshape(mesh_y, -1)
    # xyz[:, 2] = np.reshape(z_norm, -1)
    # print('xyz')
    # print(xyz)

    def normalize_depth(depth_img: np.ndarray) -> np.ndarray:
        """
        归一化深度图像：
        1. 首先将非零值归一化到[0,1]范围
        2. 然后将最小值映射到0，最大值映射到(最大值-最小值)

        :param depth_img: 深度图像
        :return: 归一化后的深度图像
        :raises ValueError: 当输入无效时抛出异常
        """
        none_zero_mask = depth_img > 0
        if not np.any(none_zero_mask):
            return np.zeros_like(depth_img, dtype=np.float32)

        min_val = np.min(depth_img[none_zero_mask])
        max_val = np.max(depth_img[none_zero_mask])

        normalized = np.zeros_like(depth_img, dtype=np.float32)
        normalized[none_zero_mask] = depth_img[none_zero_mask]
        normalized[none_zero_mask] -= min_val
        normalized[none_zero_mask] /= (max_val - min_val)
        normalized[none_zero_mask] *= img_w * scale
        return normalized

    check_img(bgr_img)
    check_img(depth_img)
    img_h, img_w = bgr_img.shape[:2]

    bgr_img = bgr_img.copy()
    bgr_img = normalize_16b_gray_to_uint8(bgr_img)
    # y轴翻转
    bgr_img = np.flipud(bgr_img)
    bgr_img = bgr_img.astype(np.float32) / 255  # convert 0~255 to 0~1

    depth_img = depth_img.copy()
    # y轴翻转
    depth_img = np.flipud(depth_img)
    depth_img = normalize_depth(depth_img)

    # 将灰度图转换为BGR图
    if len(bgr_img.shape) == 2:
        bgr_img = cv2.cvtColor(bgr_img, cv2.COLOR_GRAY2BGR)
    elif len(bgr_img.shape) == 3:
        bgr_img = bgr_img.astype(np.uint8)
    elif len(bgr_img.shape) == 4:
        bgr_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGRA2BGR)
    else:
        raise ValueError("bgr_img必须是2D（灰度）或3D（BGR）或4D（BGRD）数组")

    mesh_x, mesh_y = np.meshgrid(np.arange(img_w), np.arange(img_h))
    xyz = np.zeros((np.size(mesh_x), 3))
    xyz[:, 0] = np.reshape(mesh_x, -1)
    xyz[:, 1] = np.reshape(mesh_y, -1)
    xyz[:, 2] = np.reshape(depth_img, -1)

    xyz_rgb = np.zeros((np.size(mesh_x), 3))
    xyz_rgb[:, 0] = np.reshape(bgr_img[:, :, 0], -1)
    xyz_rgb[:, 1] = np.reshape(bgr_img[:, :, 1], -1)
    xyz_rgb[:, 2] = np.reshape(bgr_img[:, :, 2], -1)

    # 去除0值
    xyz, xyz_rgb = xyz[xyz[:, 2] > 0], xyz_rgb[xyz[:, 2] > 0]

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    pcd.colors = o3d.utility.Vector3dVector(xyz_rgb)
    return pcd
