import argparse
import glob
import json
import math
import os
from typing import Any, Dict, List, Tuple, Optional


def _normalize_direction_deg(direction_value: Any) -> float:
    try:
        direction_deg = float(direction_value)
    except Exception:
        direction_deg = 0.0
    # 归一化到 [0, 360)
    direction_deg = direction_deg % 360
    return direction_deg


def _direction_deg_to_wrapped_radian(direction_deg: float) -> float:
    # 与 labelme\dlcv\label_file.py 中的 saveRotationBox 保持一致：
    # 先转弧度，然后将范围折叠到 (-pi/2, pi/2] 以获得方向向量
    dir_rad = math.radians(direction_deg)
    while dir_rad <= -math.pi / 2:
        dir_rad += math.pi
    while dir_rad > math.pi / 2:
        dir_rad -= math.pi
    return dir_rad


def _compute_center_width_height(
    points: List[List[float]], dir_vec: Tuple[float, float]
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    cx = cy = w = h = None

    if not isinstance(points, list):
        return cx, cy, w, h

    try:
        if len(points) >= 4:
            # 中心点（四点平均）
            cx = (
                float(points[0][0])
                + float(points[1][0])
                + float(points[2][0])
                + float(points[3][0])
            ) / 4.0
            cy = (
                float(points[0][1])
                + float(points[1][1])
                + float(points[2][1])
                + float(points[3][1])
            ) / 4.0

            # 计算四条边，与方向向量的平行度（abs dot）
            edges: List[Tuple[int, float, float]] = []  # (idx, length, abs_dot)
            for i in range(4):
                j = (i + 1) % 4
                vx = float(points[j][0]) - float(points[i][0])
                vy = float(points[j][1]) - float(points[i][1])
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

        elif len(points) >= 2:
            # 退化处理（不足 4 点）：以两点轴对齐矩形估计
            x0, y0 = float(points[0][0]), float(points[0][1])
            x1, y1 = float(points[1][0]), float(points[1][1])
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            dx, dy = x1 - x0, y1 - y0
            proj_parallel = abs(dx * dir_vec[0] + dy * dir_vec[1])
            proj_perp = abs(dx * (-dir_vec[1]) + dy * dir_vec[0])
            w = max(proj_parallel, 0.0)
            h = max(proj_perp, 0.0)
    except Exception:
        # 容忍异常，返回 None 值表示无法计算
        pass

    return cx, cy, w, h


def convert_shapes_inplace(shapes: List[Dict[str, Any]]) -> bool:
    """按 saveRotationBox 的逻辑为旋转框补充/规范 direction 与 rotation_box。

    返回值表示是否对 shapes 有修改。
    """
    modified = False

    for shape in shapes or []:
        if (shape or {}).get("shape_type") != "rotation":
            continue

        # direction 处理：规范为 0-360 的浮点数
        before_direction = shape.get("direction")
        direction_deg = _normalize_direction_deg(before_direction)
        if before_direction != direction_deg:
            modified = True
        shape["direction"] = direction_deg

        # 方向弧度（折叠到 (-pi/2, pi/2]）与方向向量
        dir_rad = _direction_deg_to_wrapped_radian(direction_deg)
        dir_vec = (math.cos(dir_rad), math.sin(dir_rad))

        # 计算中心与宽高
        points = shape.get("points") or []
        cx, cy, w, h = _compute_center_width_height(points, dir_vec)

        try:
            radian_value = float(dir_rad)
        except Exception:
            radian_value = 0.0

        # 仅当全部可计算时写入 rotation_box
        if cx is not None and cy is not None and w is not None and h is not None:
            new_rotation_box = {
                "Cx": float(cx),
                "Cy": float(cy),
                "W": float(w),
                "H": float(h),
                "radian": float(radian_value),
            }
            if shape.get("rotation_box") != new_rotation_box:
                shape["rotation_box"] = new_rotation_box
                modified = True

    return modified


def process_file(json_path: str, dry_run: bool = False, backup: bool = True) -> bool:
    """处理单个 JSON 文件。返回是否修改并保存。"""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    if not isinstance(data, dict) or "shapes" not in data:
        return False

    shapes = data.get("shapes")
    if not isinstance(shapes, list):
        return False

    modified = convert_shapes_inplace(shapes)
    if not modified:
        return False

    if dry_run:
        return False

    # 备份
    if backup:
        try:
            bak_path = json_path + ".bak"
            if not os.path.exists(bak_path):
                with open(bak_path, "w", encoding="utf-8") as bf:
                    json.dump(data, bf, ensure_ascii=False, indent=2)
        except Exception:
            # 备份失败不阻止主流程
            pass

    # 保存
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def find_json_files(root: str, recursive: bool) -> List[str]:
    pattern = os.path.join(root, "**", "*.json") if recursive else os.path.join(root, "*.json")
    return [p for p in glob.glob(pattern, recursive=recursive) if os.path.isfile(p)]


def main():
    parser = argparse.ArgumentParser(
        description="批量为旋转框补充 direction 与 rotation_box（兼容 labelme dlcv saveRotationBox 逻辑）"
    )
    parser.add_argument("input_dir", help="包含标注 JSON 的目录")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="递归遍历子目录",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不生成 .bak 备份文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行，不落盘，仅统计可修改的文件数",
    )

    args = parser.parse_args()

    json_files = find_json_files(args.input_dir, recursive=bool(args.recursive))
    total = len(json_files)
    changed = 0

    for path in json_files:
        if process_file(path, dry_run=bool(args.dry_run), backup=not bool(args.no_backup)):
            changed += 1

    print(f"共发现 {total} 个 JSON 文件，修改 {changed} 个。dry_run={bool(args.dry_run)}")


if __name__ == "__main__":
    main()


