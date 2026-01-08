import numpy as np
import cv2

from pyqttoast import Toast, ToastPreset, ToastPosition

Toast.setPosition(ToastPosition.TOP_MIDDLE)


def cv_imread(file_path) -> np.ndarray:
    if isinstance(file_path, str):
        file_path = file_path.encode("utf-8")
    cv_img = cv2.imdecode(
        np.fromfile(file_path, dtype=np.uint8),
        cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH,
    )
    return cv_img


def notification(title=None, text=None, preset: ToastPreset = ToastPreset.INFORMATION, duration: int = 2000):
    toast = Toast()
    toast.setDuration(duration)

    if title:
        toast.setTitle(title)

    if text:
        toast.setText(text)

    toast.applyPreset(preset)
    toast.show()


def normalize_16b_gray_to_uint8(bgr_img: np.ndarray) -> np.ndarray:
    """
    归一化16位图像到8位显示
    1. 如果是BGR图像，先转换为灰度图
    2. 只对非零值进行归一化，将非零最小值映射到0，最大值映射到255

    :param bgr_img: 16位灰度图像或BGR图像，支持的数据类型：uint8, uint16, float32, float64
    :return: 归一化后的8位图像
    """
    # 输入验证
    if not isinstance(bgr_img, np.ndarray):
        raise ValueError("输入必须是numpy数组")

    # 如果已经是8位图像，直接返回
    if bgr_img.dtype == np.uint8:
        return bgr_img

    if bgr_img.size == 0:
        raise ValueError("输入数组不能为空")

    # 检查数据类型
    if bgr_img.dtype not in (np.uint8, np.uint16, np.float32, np.float64):
        raise ValueError(f"不支持的数据类型: {bgr_img.dtype}，支持的类型: uint8, uint16, float32, float64")

    # 检查无效值
    if np.any(np.isnan(bgr_img)) or np.any(np.isinf(bgr_img)):
        raise ValueError("输入图像包含无效值（NaN或Inf）")

    # 如果是BGR图像，转换为灰度图
    if bgr_img.ndim == 3:
        if bgr_img.shape[2] != 3:
            raise ValueError("3通道图像必须是BGR格式")
        bgr_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)

    # 获取非零像素的索引
    none_zero_mask = bgr_img > 0

    # 如果没有非零像素，返回全零图像
    if not np.any(none_zero_mask):
        return np.zeros_like(bgr_img, dtype=np.uint8)

    # 获取非零像素的最小值和最大值
    min_val = np.min(bgr_img[none_zero_mask])
    max_val = np.max(bgr_img[none_zero_mask])

    # 如果所有非零像素值相同，返回二值图像
    if max_val == min_val:
        result = np.zeros_like(bgr_img, dtype=np.uint8)
        result[none_zero_mask] = 255
        return result

    # 归一化处理 - 使用原地操作减少内存使用
    normalized = np.zeros_like(bgr_img, dtype=np.float32)
    valid_pixels = bgr_img[none_zero_mask]
    normalized[none_zero_mask] = valid_pixels
    normalized[none_zero_mask] -= min_val
    normalized[none_zero_mask] /= (max_val - min_val)
    normalized[none_zero_mask] *= 255
    normalized = normalized.astype(np.uint8)
    return normalized


if __name__ == "__main__":
    from labelme.dlcv.widget_25d_3d.tests import gray_img_path, depth_img_path

    raw_gray_img = cv2.imread(gray_img_path, cv2.IMREAD_UNCHANGED)
    normalized_gray_img = normalize_16b_gray_to_uint8(raw_gray_img)

    cv2.imwrite("normalized_gray_img.png", normalized_gray_img)
