import base64
import json
import locale
import logging
import math
import os
import tempfile
from pathlib import Path

from labelme import __version__
from labelme.label_file import *

try:
    from dlcv_core.image_json import SUPPORTED_IMAGE_EXTENSIONS
    from dlcv_core.image_json import UnsupportedImageFormatError
    from dlcv_core.image_json import has_image_json
    from dlcv_core.image_json import read_image_json
    from dlcv_core.image_json import remove_image_json
    from dlcv_core.image_json import write_image_json
    IMAGE_JSON_AVAILABLE = True
    IMAGE_JSON_LIMITATION = None
except ModuleNotFoundError as exc:
    if exc.name not in {"dlcv_core", "dlcv_core.image_json"}:
        raise
    IMAGE_JSON_AVAILABLE = False
    IMAGE_JSON_LIMITATION = (
        "当前 dlcv_core 不含图片内 JSON 接口；LabelMeAI 仅可读写外部 JSON，"
        "无法读取仅保存在图片内的标注。"
    )
    SUPPORTED_IMAGE_EXTENSIONS = frozenset()
    logging.getLogger(__name__).warning(IMAGE_JSON_LIMITATION)

    class UnsupportedImageFormatError(ValueError):
        pass

    def has_image_json(_path):
        return False

    def remove_image_json(path, output_path=None):
        return Path(output_path) if output_path is not None else Path(path)


def _read_sidecar(path):
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode(locale.getencoding())
    return json.loads(text)


def _read_embedded(path):
    try:
        return read_image_json(path)
    except UnsupportedImageFormatError:
        return None


def select_annotation_source(image_path, sidecar_path):
    """选择实际标注来源，受支持容器的读取错误直接向上报告。"""
    image_path = Path(image_path)
    sidecar_path = Path(sidecar_path)
    if (
        IMAGE_JSON_AVAILABLE
        and image_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ):
        try:
            if has_image_json(image_path):
                return image_path
        except UnsupportedImageFormatError:
            pass
    if sidecar_path.is_file():
        return sidecar_path
    return None


def _write_sidecar(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            encoding="utf-8",
            newline="\n",
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            try:
                os.chmod(temp_path, path.stat().st_mode)
            except OSError:
                pass
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _path_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _group_image_names(other_data):
    names = []
    for key in ("img_name_list", "image_path_list"):
        value = (other_data or {}).get(key)
        if not isinstance(value, (list, tuple)):
            continue
        names.extend(name for name in value if isinstance(name, str) and name)
    return names


def _collect_image_paths(primary_image, other_data):
    candidates = [primary_image]
    candidates.extend(
        primary_image.parent / name for name in _group_image_names(other_data)
    )
    image_paths = {}
    for path in candidates:
        image_paths.setdefault(_path_key(path), Path(path))
    return list(image_paths.values())


def _rebase_embedded_data(data, primary_image, image_path):
    embedded = dict(data)
    embedded["imagePath"] = image_path.name
    for key in ("img_name_list", "image_path_list"):
        value = embedded.get(key)
        if not isinstance(value, (list, tuple)):
            continue
        embedded[key] = [
            os.path.relpath(primary_image.parent / name, image_path.parent)
            if isinstance(name, str) and name else name
            for name in value
        ]
    return embedded


def _new_temp_path(path, suffix):
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=suffix,
        delete=False,
    ) as file:
        return Path(file.name)


def _cleanup_temp_paths(paths):
    for temp_path in paths:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).exception(
                "清理临时标注文件失败：%s", temp_path
            )


def _commit_image_candidates(candidates, sidecar_path):
    backups = {}
    rollback_failed = False
    try:
        for image_path, candidate in candidates.items():
            backup = _new_temp_path(image_path, ".backup")
            try:
                os.replace(image_path, backup)
            except Exception:
                backup.unlink(missing_ok=True)
                raise
            backups[image_path] = backup
            os.replace(candidate, image_path)
        if sidecar_path.exists():
            sidecar_path.unlink()
    except Exception as exc:
        rollback_errors = []
        for image_path, backup in reversed(list(backups.items())):
            try:
                os.replace(backup, image_path)
            except Exception as rollback_exc:
                rollback_errors.append((image_path, backup, rollback_exc))
        if rollback_errors:
            rollback_failed = True
            failed_paths = ", ".join(str(item[0]) for item in rollback_errors)
            raise RuntimeError(f"恢复原图片失败：{failed_paths}") from exc
        raise
    finally:
        _cleanup_temp_paths(candidates.values())
        if not rollback_failed:
            _cleanup_temp_paths(backups.values())


def _write_embedded_group(image_paths, data, primary_image):
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
                _rebase_embedded_data(data, primary_image, image_path),
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


def remove_image_annotations(image_paths, sidecar_path):
    """清除一组图片内标注；任一步失败时恢复已替换的图片。"""
    sidecar_path = Path(sidecar_path)
    candidates = {}
    removed_paths = []
    unique_paths = {}
    for image_path in image_paths:
        image_path = Path(image_path)
        unique_paths.setdefault(_path_key(image_path), image_path)

    try:
        if IMAGE_JSON_AVAILABLE:
            for image_path in unique_paths.values():
                if not image_path.is_file():
                    continue
                try:
                    embedded = has_image_json(image_path)
                except UnsupportedImageFormatError:
                    continue
                if not embedded:
                    continue
                candidate = _new_temp_path(image_path, ".candidate")
                candidates[image_path] = candidate
                remove_image_json(image_path, output_path=candidate)
                removed_paths.append(str(image_path))
    except Exception as exc:
        _cleanup_temp_paths(candidates.values())
        raise LabelFileError(exc) from exc

    sidecar_existed = sidecar_path.exists()
    try:
        _commit_image_candidates(candidates, sidecar_path)
    except Exception as exc:
        raise LabelFileError(exc) from exc
    if sidecar_existed:
        removed_paths.insert(0, str(sidecar_path))
    return removed_paths


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
            embedded_source = False
            if (
                IMAGE_JSON_AVAILABLE
                and source_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            ):
                data = _read_embedded(source_path)
                embedded_source = isinstance(data, dict)
                if not isinstance(data, dict):
                    sidecar = source_path.with_suffix(".json")
                    data = _read_sidecar(sidecar)
                    source_path = sidecar
            else:
                data = _read_sidecar(source_path)
                if IMAGE_JSON_AVAILABLE:
                    image_path = source_path.parent / data.get("imagePath", "")
                    if image_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                        embedded = _read_embedded(image_path)
                        if isinstance(embedded, dict):
                            data = embedded
                            source_path = image_path
                            embedded_source = True
            if not isinstance(data, dict):
                raise LabelFileError(f"标注不是 JSON 对象：{filename}")

            flags = data.get("flags") or {}
            imagePath = (source_path.name if embedded_source else data["imagePath"])
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
    ):
        # 添加处理旋转框的方向属性
        shapes = self.saveRotationBox(shapes)
        
        # 标注保存入口可能收到上次加载的图片路径，不能直接按文本写入。
        sidecar_path = Path(filename).with_suffix(".json")
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
            if not IMAGE_JSON_AVAILABLE:
                _write_sidecar(sidecar_path, data)
                self.filename = str(sidecar_path)
                return
            primary_image = Path(os.path.abspath(sidecar_path.parent / imagePath))
            image_paths = _collect_image_paths(primary_image, otherData)
            saved_paths, unsupported_paths, failures = _write_embedded_group(
                image_paths, data, primary_image
            )
            # 外部文件默认共存；关闭设置后，内嵌失败仍保存外部备份。
            backup_saved = False
            if save_external_json or unsupported_paths or failures:
                try:
                    _write_sidecar(sidecar_path, data)
                    backup_saved = True
                except Exception as exc:
                    failures.append((sidecar_path, exc))
            if failures:
                failed_details = "; ".join(
                    f"{path}: {error}" for path, error in failures
                )
                backup_message = (
                    f"最新标注已保存至外部 JSON：{sidecar_path}。"
                    if backup_saved else "外部 JSON 备份未完成。"
                )
                raise LabelFileError(
                    f"标注保存未全部完成，已更新 {len(saved_paths)} 张图片。"
                    f"{backup_message}失败文件：{failed_details}"
                )
            self.filename = str(
                primary_image if primary_image in saved_paths else sidecar_path
            )
        except Exception as exc:
            raise LabelFileError(exc) from exc

    def load_shapes(self, shapes, s, parsers=None):
        shapes = super().load_shapes(shapes, s, parsers)
        
        # 加载旋转框的方向属性
        shapes = self.loadRotationBox(shapes, s)
        
        return shapes
