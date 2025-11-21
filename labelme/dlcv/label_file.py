from labelme.label_file import *
import math


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
            with open(filename, "r") as f:
                data = json.load(f)

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
        self.filename = filename
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
                if cx is not None and cy is not None and w is not None and h is not None:
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
    ):
        # 添加处理旋转框的方向属性
        shapes = self.saveRotationBox(shapes)
        
        return super().save(
            filename=filename,
            shapes=shapes,
            imagePath=imagePath,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
            imageData=imageData,
            otherData=otherData,
            flags=flags,
        )

    def load_shapes(self, shapes, s, parsers=None):
        shapes = super().load_shapes(shapes, s, parsers)
        
        # 加载旋转框的方向属性
        shapes = self.loadRotationBox(shapes, s)
        
        return shapes
