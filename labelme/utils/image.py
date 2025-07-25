# MIT License
# Copyright (c) Kentaro Wada

import base64
import io

import PIL.ExifTags
import PIL.Image
import PIL.ImageOps
import numpy as np


def img_data_to_pil(img_data):
    f = io.BytesIO()
    f.write(img_data)
    img_pil = PIL.Image.open(f)
    return img_pil


def img_data_to_arr(img_data):
    img_pil = img_data_to_pil(img_data)
    img_arr = np.array(img_pil)
    return img_arr


def img_b64_to_arr(img_b64):
    img_data = base64.b64decode(img_b64)
    img_arr = img_data_to_arr(img_data)
    return img_arr


def img_pil_to_data(img_pil):
    f = io.BytesIO()
    img_pil.save(f, format="PNG")
    img_data = f.getvalue()
    return img_data


def img_arr_to_b64(img_arr):
    img_data = img_arr_to_data(img_arr)
    img_b64 = base64.b64encode(img_data).decode("utf-8")
    return img_b64


def img_arr_to_data(img_arr):
    img_pil = PIL.Image.fromarray(img_arr)
    img_data = img_pil_to_data(img_pil)
    return img_data


def img_data_to_png_data(img_data):
    with io.BytesIO() as f:
        f.write(img_data)
        img = PIL.Image.open(f)

        with io.BytesIO() as f:
            img.save(f, "PNG")
            f.seek(0)
            return f.read()


def img_qt_to_arr(img_qt):
    w, h, d = img_qt.size().width(), img_qt.size().height(), img_qt.depth()
    bytes_ = img_qt.bits().asstring(w * h * d // 8)
    img_arr = np.frombuffer(bytes_, dtype=np.uint8).reshape((h, w, d // 8))
    return img_arr


def apply_exif_orientation(image):
    try:
        exif = image._getexif()
    except AttributeError:
        exif = None

    if exif is None:
        return image

    exif = {PIL.ExifTags.TAGS[k]: v for k, v in exif.items() if k in PIL.ExifTags.TAGS}

    orientation = exif.get("Orientation", None)

    if orientation == 1:
        # do nothing
        return image
    elif orientation == 2:
        # left-to-right mirror
        return PIL.ImageOps.mirror(image)
    elif orientation == 3:
        # rotate 180
        return image.transpose(PIL.Image.ROTATE_180)
    elif orientation == 4:
        # top-to-bottom mirror
        return PIL.ImageOps.flip(image)
    elif orientation == 5:
        # top-to-left mirror
        return PIL.ImageOps.mirror(image.transpose(PIL.Image.ROTATE_270))
    elif orientation == 6:
        # rotate 270
        return image.transpose(PIL.Image.ROTATE_270)
    elif orientation == 7:
        # top-to-right mirror
        return PIL.ImageOps.mirror(image.transpose(PIL.Image.ROTATE_90))
    elif orientation == 8:
        # rotate 90
        return image.transpose(PIL.Image.ROTATE_90)
    else:
        return image


# 额外添加的代码
from qtpy.QtGui import QImage


def numpy_to_qimage(array: np.ndarray) -> QImage:
    # 确保数组是 uint16 类型
    if array.dtype == np.uint16:
        # 将 uint16 转换为 uint8
        # 假设数据范围在 0 到 65535 之间
        array = (array / 256).astype(np.uint8)  # 将 uint16 范围缩小到 uint8

    height, width, channel = array.shape

    # 根据通道数创建 QImage
    if channel == 1:  # 灰度图
        return QImage(array.data, width, height, width, QImage.Format_Grayscale8)
    elif channel == 3:  # RGB 图
        return QImage(array.data, width, height, width * 3, QImage.Format_RGB888)
    elif channel == 4:  # RGBA 图
        return QImage(array.data, width, height, width * 4, QImage.Format_RGBA8888)
    else:
        raise ValueError("Unsupported channel number: {}".format(channel))
