# flake8: noqa

from ._io import lblsave

from .image import apply_exif_orientation
from .image import img_arr_to_b64
from .image import img_arr_to_data
from .image import img_b64_to_arr
from .image import img_data_to_arr
from .image import img_data_to_pil
from .image import img_data_to_png_data
from .image import img_pil_to_data
from .image import img_qt_to_arr

from .shape import labelme_shapes_to_label
from .shape import masks_to_bboxes
from .shape import polygons_to_mask
from .shape import shape_to_mask
from .shape import shapes_to_label

from .qt import newIcon
from .qt import newButton
from .qt import newAction
from .qt import addActions
from .qt import labelValidator
from .qt import struct
from .qt import distance
from .qt import distancetoline
from .qt import fmtShortcut

import time
from labelme.logger import logger


def print_time(last_time, desc='time elapsed'):
    cur_time = time.time()
    # print ms
    logger.info(f'{desc}: {(time.time() - last_time) * 1000:.2f} ms')
    return cur_time
