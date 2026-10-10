import base64
import json
import locale
import math
import os
from io import BytesIO
from pathlib import Path

from labelme import __version__
from labelme.label_file import *

from dlcv_core.image_json import SUPPORTED_IMAGE_EXTENSIONS
from dlcv_core.image_json import UnsupportedImageFormatError
from dlcv_core.image_json import has_image_json
from dlcv_core.image_json import remove_image_json
from dlcv_core.image_json import write_image_json


def read_sidecar(path):
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode(locale.getencoding())
    data = json.loads(text)
    if not isinstance(data, dict):
        raise LabelFileError(f"标注不是 JSON 对象：{path}")
    return data


def select_annotation_source(image_path, sidecar_path):
    """正常业务只读取外部 JSON，缺失时不使用图片内标注。"""
    sidecar_path = Path(sidecar_path)
    return sidecar_path if sidecar_path.is_file() else None


def resolve_sidecar_path(image_path, window, *, use_loaded=True):
    """当前图片沿用已加载 JSON；其他图片按项目路径和输出目录确定。"""
    if use_loaded:
        loaded_sidecar = getattr(
            getattr(window, "labelFile", None), "sidecar_path", None
        )
        # 导入目录只清空 filename，画布仍保留 imagePath 对应的已加载标注。
        loaded_image = (
            getattr(window, "filename", None) or getattr(window, "imagePath", None)
        )
        if (
            loaded_sidecar and loaded_image
            and _path_key(image_path) == _path_key(loaded_image)
        ):
            return Path(loaded_sidecar)
    sidecar = Path(window.proj_manager.get_json_path(str(image_path)))
    output_dir = getattr(window, "output_dir", None)
    return Path(output_dir) / sidecar.name if output_dir else sidecar


def _write_buffer(path, buffer):
    original = path.read_bytes() if path.exists() else None
    opened = False
    try:
        with path.open("wb") as file:
            opened = True
            view = buffer.getbuffer()
            try:
                if file.write(view) != len(view):
                    raise OSError(f"文件内容未完整写入：{path}")
            finally:
                view.release()
            file.flush()
            os.fsync(file.fileno())
    except Exception as exc:
        if opened:
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            except OSError as restore_error:
                raise OSError(
                    f"文件写入失败且原内容恢复失败：{path}：{restore_error}"
                ) from exc
        raise


def _write_sidecar(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    with BytesIO(text.encode("utf-8")) as buffer:
        _write_buffer(path, buffer)


def _path_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _collect_image_paths(primary_image, other_data, sidecar_path=None):
    sidecar_path = (
        Path(sidecar_path) if sidecar_path is not None
        else primary_image.with_suffix(".json")
    )
    candidates = [primary_image]
    for key, directory in (
        ("img_name_list", primary_image.parent),
        ("image_path_list", sidecar_path.parent),
    ):
        names = (other_data or {}).get(key)
        if isinstance(names, (list, tuple)):
            candidates.extend(
                directory / name for name in names
                if isinstance(name, str) and name
            )
    image_paths = {}
    for path in candidates:
        image_paths.setdefault(_path_key(path), Path(path))
    return list(image_paths.values())


def _rebase_embedded_data(data, primary_image, image_path, sidecar_path):
    embedded = dict(data)
    embedded["imagePath"] = image_path.name
    for key, directory in (
        ("img_name_list", primary_image.parent),
        ("image_path_list", sidecar_path.parent),
    ):
        value = embedded.get(key)
        if not isinstance(value, (list, tuple)):
            continue
        embedded[key] = [
            os.path.relpath(directory / name, image_path.parent)
            if isinstance(name, str) and name else name
            for name in value
        ]
    return embedded


def _write_embedded_group(image_paths, data, primary_image, sidecar_path):
    """逐图保存内嵌标注，单张失败不撤回其他图片的最新数据。"""
    saved_paths = []
    unsupported_paths = []
    failures = []
    for image_path in image_paths:
        if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            unsupported_paths.append(image_path)
            continue
        try:
            write_image_json(
                image_path,
                _rebase_embedded_data(data, primary_image, image_path, sidecar_path),
                ensure_ascii=False,
                indent=2,
            )
        except UnsupportedImageFormatError:
            unsupported_paths.append(image_path)
        except Exception as exc:
            failures.append((image_path, exc))
        else:
            saved_paths.append(image_path)
    return saved_paths, unsupported_paths, failures


def remove_image_annotations(image_paths, sidecar_path, default_sidecar_path=None):
    """只清理已知标注位置；清理失败时恢复已修改内容。"""
    sidecar_paths = {_path_key(sidecar_path): Path(sidecar_path)}
    if default_sidecar_path is not None:
        sidecar_paths.setdefault(_path_key(default_sidecar_path), Path(default_sidecar_path))
    originals = {}
    changed_paths = []
    unique_paths = {}
    for image_path in image_paths:
        image_path = Path(image_path)
        unique_paths.setdefault(_path_key(image_path), image_path)
        image_sidecar = image_path.with_suffix(".json")
        sidecar_paths.setdefault(_path_key(image_sidecar), image_sidecar)

    try:
        for image_path in unique_paths.values():
            if not image_path.is_file():
                continue
            try:
                embedded = has_image_json(image_path)
            except UnsupportedImageFormatError:
                continue
            if embedded:
                originals[image_path] = BytesIO(image_path.read_bytes())

        for image_path in originals:
            changed_paths.append(image_path)
            remove_image_json(image_path)
        for sidecar_path in sidecar_paths.values():
            if sidecar_path.exists():
                originals[sidecar_path] = BytesIO(sidecar_path.read_bytes())
                sidecar_path.unlink()
                changed_paths.append(sidecar_path)
    except Exception as exc:
        restore_errors = []
        for image_path in reversed(changed_paths):
            try:
                _write_buffer(image_path, originals[image_path])
            except Exception as restore_exc:
                restore_errors.append(f"{image_path}: {restore_exc}")
        if restore_errors:
            raise LabelFileError(
                f"清理标注失败：{exc}；恢复原图片失败：{'; '.join(restore_errors)}"
            ) from exc
        raise LabelFileError(exc) from exc
    finally:
        for buffer in originals.values():
            buffer.close()

    return [str(path) for path in changed_paths]


class LabelFile(LabelFile):

    def load(self, filename):
        keys = [
            "version",
            "imageData",
            "imagePath",
            "shapes",  # polygonal annotations
            "flags",  # image level flags
            "imageHeight",
            "imageWidth",
        ]
        shape_keys = [
            "label",
            "points",
            "group_id",
            "shape_type",
            "flags",
            "description",
            "mask",
        ]
        try:
            source_path = Path(filename)
            if source_path.suffix.lower() != ".json":
                source_path = source_path.with_suffix(".json")
            self.sidecar_path = str(source_path)
            data = read_sidecar(source_path)
            flags = data.get("flags") or {}
            imagePath = data["imagePath"]
            shapes = [
                dict(
                    label=s["label"],
                    points=s["points"],
                    shape_type=s.get("shape_type", "polygon"),
                    flags=s.get("flags", {}),
                    description=s.get("description"),
                    group_id=s.get("group_id"),
                    mask=utils.img_b64_to_arr(s["mask"]).astype(bool)
                    if s.get("mask")
                    else None,
                    other_data={k: v for k, v in s.items() if k not in shape_keys},
                )
                for s in data["shapes"]
            ]
        except Exception as e:
            raise LabelFileError(e)

        otherData = {}
        for key, value in data.items():
            if key not in keys:
                otherData[key] = value

        # Only replace data after everything is loaded.
        self.flags = flags
        self.shapes = shapes
        self.imagePath = imagePath
        self.imageData = None  # 2024年10月20日14:37:58 cyf修改, 弃用 imageData
        self.filename = str(source_path)
        self.otherData = otherData

    # 修改该函数是为了 https://bbs.dlcv.ai/t/topic/328
    @staticmethod
    def load_image_file(filename):
        return None

    def saveRotationBox(self, shapes):
        """保存旋转框标注的方向属性"""
        for shape in shapes:
            if shape.get("shape_type") == "rotation":
                # 确保所有旋转框都有direction属性
                if "direction" not in shape:
                    shape["direction"] = 0.0  # 默认方向为0度
                else:
                    # 确保direction值是浮点数
                    shape["direction"] = float(shape["direction"])
                    # 确保方向在0-360之间
                    shape["direction"] = shape["direction"] % 360

                # 新增：为旋转框写入一个独立字段，保存 Cx、Cy、W、H 与弧度
                pts = shape.get("points") or []
                cx = cy = w = h = None
                # 方向（度）与方向向量
                try:
                    dir_deg = float(shape.get("direction", 0.0))
                except Exception:
                    dir_deg = 0.0
                dir_rad = math.radians(dir_deg)
                while dir_rad <= -math.pi / 2:
                    dir_rad += math.pi
                while dir_rad > math.pi / 2:
                    dir_rad -= math.pi
                dir_vec = (math.cos(dir_rad), math.sin(dir_rad))

                if isinstance(pts, list):
                    try:
                        if len(pts) >= 4:
                            # 中心点
                            cx = (
                                float(pts[0][0])
                                + float(pts[1][0])
                                + float(pts[2][0])
                                + float(pts[3][0])
                            ) / 4.0
                            cy = (
                                float(pts[0][1])
                                + float(pts[1][1])
                                + float(pts[2][1])
                                + float(pts[3][1])
                            ) / 4.0

                            # 四条边向量与长度
                            edges = []  # (idx, length, abs_dot)
                            for i in range(4):
                                j = (i + 1) % 4
                                vx = float(pts[j][0]) - float(pts[i][0])
                                vy = float(pts[j][1]) - float(pts[i][1])
                                length = math.hypot(vx, vy)
                                if length <= 0:
                                    continue
                                ux, uy = vx / length, vy / length
                                abs_dot = abs(ux * dir_vec[0] + uy * dir_vec[1])
                                edges.append((i, length, abs_dot))

                            if edges:
                                # 与方向最平行的边定义为 W
                                w_edge = max(edges, key=lambda e: e[2])
                                w = w_edge[1]
                                # 与方向最垂直的边定义为 H
                                h_edge = min(edges, key=lambda e: e[2])
                                h = h_edge[1]
                        elif len(pts) >= 2:
                            # 退化处理（不足 4 点）：以两点轴对齐矩形估计
                            x0, y0 = float(pts[0][0]), float(pts[0][1])
                            x1, y1 = float(pts[1][0]), float(pts[1][1])
                            cx = (x0 + x1) / 2.0
                            cy = (y0 + y1) / 2.0
                            dx, dy = x1 - x0, y1 - y0
                            # 将边向量投影到方向与其垂直方向
                            proj_parallel = abs(dx * dir_vec[0] + dy * dir_vec[1])
                            proj_perp = abs(dx * (-dir_vec[1]) + dy * dir_vec[0])
                            w = max(proj_parallel, 0.0)
                            h = max(proj_perp, 0.0)
                    except Exception:
                        pass

                # 弧度：与用户标注方向一致，直接由 direction 转弧度
                try:
                    rad = float(dir_rad)
                except Exception:
                    rad = 0.0

                # 仅当成功计算出中心和宽高时写入该字段
                if (
                    cx is not None
                    and cy is not None
                    and w is not None
                    and h is not None
                ):
                    shape["rotation_box"] = {
                        "Cx": float(cx),
                        "Cy": float(cy),
                        "W": float(w),
                        "H": float(h),
                        "radian": float(rad),
                    }
        return shapes
    
    def loadRotationBox(self, shapes, s):
        """加载旋转框的方向属性"""
        if s.shape_type == "rotation":
            # 确保shape对象中有direction属性
            if "direction" in shapes[-1]:
                # 从JSON文件中读取direction值并设置到Shape对象
                s.direction = float(shapes[-1]["direction"])
                # 确保方向在0-360之间
                s.direction = s.direction % 360
            else:
                # 如果没有direction属性，设置默认值
                s.direction = 0.0
            
            # 检查并修复旋转框的点数
            if len(s.points) != 4:
                # 如果点数不是4个，尝试修复
                if len(s.points) >= 2:
                    # 如果至少有两个点，可以尝试构建矩形
                    x_values = [p.x() for p in s.points]
                    y_values = [p.y() for p in s.points]
                    
                    # 计算边界框
                    x_min, x_max = min(x_values), max(x_values)
                    y_min, y_max = min(y_values), max(y_values)
                    
                    # 创建四个角点
                    s.points = [
                        QtCore.QPointF(x_min, y_min),  # 左上
                        QtCore.QPointF(x_max, y_min),  # 右上
                        QtCore.QPointF(x_max, y_max),  # 右下
                        QtCore.QPointF(x_min, y_max),  # 左下
                    ]
                    # 更新标签为与点数量相同
                    s.point_labels = [1, 1, 1, 1]
                elif len(s.points) == 1:
                    # 如果只有一个点，创建一个小矩形（可能不理想但至少能显示）
                    point = s.points[0]
                    x, y = point.x(), point.y()
                    size = 10  # 小矩形的大小
                    
                    s.points = [
                        QtCore.QPointF(x-size, y-size),  # 左上
                        QtCore.QPointF(x+size, y-size),  # 右上
                        QtCore.QPointF(x+size, y+size),  # 右下
                        QtCore.QPointF(x-size, y+size),  # 左下
                    ]
                    s.point_labels = [1, 1, 1, 1]
                else:
                    # 如果没有点，创建一个默认矩形
                    s.points = [
                        QtCore.QPointF(0, 0),     # 左上
                        QtCore.QPointF(100, 0),   # 右上
                        QtCore.QPointF(100, 100), # 右下
                        QtCore.QPointF(0, 100),   # 左下
                    ]
                    s.point_labels = [1, 1, 1, 1]
                
        return shapes

    def save(
        self,
        filename,
        shapes,
        imagePath,
        imageHeight,
        imageWidth,
        imageData=None,
        otherData=None,
        flags=None,
        *,
        save_external_json=True,
        source_sidecar_path=None,
    ):
        # 添加处理旋转框的方向属性
        shapes = self.saveRotationBox(shapes)
        
        # 标注保存入口可能收到上次加载的图片路径，不能直接按文本写入。
        input_path = Path(filename)
        if input_path.suffix.lower() == ".json":
            sidecar_path = input_path
        else:
            sidecar_path = Path(
                getattr(self, "sidecar_path", None) or input_path.with_suffix(".json")
            )
            imagePath = os.path.relpath(input_path, sidecar_path.parent)
        if imageData is not None:
            imageData = base64.b64encode(imageData).decode("utf-8")
            imageHeight, imageWidth = self._check_image_height_and_width(
                imageData, imageHeight, imageWidth
            )
        data = dict(
            version=__version__, flags=flags or {}, shapes=shapes,
            imagePath=imagePath, imageData=imageData,
            imageHeight=imageHeight, imageWidth=imageWidth,
        )
        for key, value in (otherData or {}).items():
            if key in data:
                raise LabelFileError(f"重复的标注字段：{key}")
            data[key] = value
        try:
            source_sidecar = Path(
                source_sidecar_path or getattr(self, "sidecar_path", None) or sidecar_path
            )
            members = data.get("image_path_list")
            if isinstance(members, (list, tuple)):
                data["image_path_list"] = [
                    os.path.relpath(source_sidecar.parent / name, sidecar_path.parent)
                    if isinstance(name, str) and name else name
                    for name in members
                ]
            primary_image = Path(os.path.abspath(sidecar_path.parent / imagePath))
            image_paths = _collect_image_paths(primary_image, data, sidecar_path)
            saved_paths, _, failures = _write_embedded_group(
                image_paths, data, primary_image, sidecar_path
            )
            # 外部 JSON 是业务读取来源，旧设置也不能跳过同步保存。
            external_saved = False
            try:
                _write_sidecar(sidecar_path, data)
                external_saved = True
            except Exception as exc:
                failures.append((sidecar_path, exc))
            if failures:
                failed_details = "; ".join(
                    f"{path}: {error}" for path, error in failures
                )
                external_message = (
                    f"最新标注已保存至外部 JSON：{sidecar_path}。"
                    if external_saved else "外部 JSON 保存未完成。"
                )
                raise LabelFileError(
                    f"标注保存未全部完成，已更新 {len(saved_paths)} 张图片。"
                    f"{external_message}失败文件：{failed_details}"
                ) from failures[0][1]
            self.sidecar_path = str(sidecar_path)
            self.filename = str(sidecar_path)
        except Exception as exc:
            raise LabelFileError(exc) from exc

    def load_shapes(self, shapes, s, parsers=None):
        shapes = super().load_shapes(shapes, s, parsers)
        
        # 加载旋转框的方向属性
        shapes = self.loadRotationBox(shapes, s)
        
        return shapes
