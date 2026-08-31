# Copy / Paste 质量指标

范围：`labelme/dlcv/utils/clip_paste.py`、`labelme/dlcv/widget/clipboard.py` 的形状 JSON 路径。

## 门禁

| 指标 | 阈值 | 命令 |
| --- | --- | --- |
| 单元测试 | 全绿 | `make test-copy-paste` |
| 行覆盖率 `clip_paste.py` | ≥ 90% | `make coverage-copy-paste` |
| Gherkin 场景 | 全绿 | pytest-bdd `tests/features/copy_paste_polygon.feature` |
| 变异测试（clip_paste） | kill ≥ 80% | `make mutate-copy-paste`（cosmic-ray；Windows 上 mutmut 不可用） |
| ruff | 无新增 E/F | `make lint` |

## 覆盖重点

1. Ctrl+C 分流：选中 → 多边形，未选中 → 图片
2. 同图偏移 5px / 异图原坐标
3. 跟随鼠标：union 左上角
4. shapely 裁切：部分超边、全部在外、折线、矩形、点
5. `copied_shapes.json` 读写与 `clear_copied_shapes`

## 报告

`make qa-copy-paste` 写出：

- `.qa-reports/coverage-copy-paste.json`
- `.qa-reports/mutation-copy-paste.json`
- 终端汇总 pass/fail

Windows 上 `mutmut` 官方不支持（需 WSL）。本仓库用 `cosmic-ray` 做变异测试。完整 session 较慢，建议本地按 `make mutate-copy-paste` 单独跑。

