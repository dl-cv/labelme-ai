# AGENTS.md

本仓库给 coding agent 的项目规则。细节索引见 [`.agent/manifest.yaml`](.agent/manifest.yaml)。

工作方式（Uncle Bob gauntlet，本项目落地）：**人负责场景和门禁，不负责逐行审纯函数实现。** 逻辑过确定性检查才算完成。Qt 壳层（`app.py`、widget 交互、闪退观感）测试拦不住，仍要人看 diff 或点一次主路径。

完整约定：[`.agent/architecture/agent-gauntlet/README.md`](.agent/architecture/agent-gauntlet/README.md)

## 硬规则

- 改已有源码用局部替换，禁止整文件重写把 **LF 写成 CRLF**。写完比 `git diff --stat` 与 `git diff -w --stat`。
- **只改 `labelme/dlcv/`**。`labelme/app.py`、`labelme/widgets/`、`labelme/config/` 是上游旧版 labelme，不要改。产品行为用 dlcv 覆盖、隐藏、接线。
- 新功能逻辑放 `labelme/dlcv/` 的 utils / mixin，**不要堆上游 `labelme/app.py`**。
- QAction 的新增、改文案、隐藏、摘菜单/工具栏、shortcut、初始化：一律放 [`labelme/dlcv/app.py`](labelme/dlcv/app.py) 的 `_init_ui`（或它调用的 `_init_*`）。不要写在 `MainWindow.__init__` 里。上游仍有的废弃 action（如 Duplicate）在 `_init_ui` 里 `removeAction` + 从 `actions.tool/menu/editMenu` 剔除 + `populateModeActions()`。
- 任务按模块切：一次只动一条行为边界。规格、实现、清理、变异测试不要塞进同一轮「改完整个 app」。
- Prompt / 本文件只放短规则。质量靠测试和工具，不靠越写越长的 `AGENTS.md`。

## 现成门禁（复制粘贴）

范围：`labelme/dlcv/utils/clip_paste.py`、clipboard 形状 JSON。文档：`docs/qa/`。

| 门 | 命令 |
| --- | --- |
| 单测 + Gherkin | `make test-copy-paste` |
| 行覆盖 `clip_paste` ≥ 90% | `make coverage-copy-paste` |
| 变异测试 kill ≥ 80%（cosmic-ray，不用 mutmut） | `make mutate-copy-paste` |
| 汇总 | `make qa-copy-paste` |
| lint | `make lint` |

Gherkin：`tests/features/copy_paste_polygon.feature`  
步骤：`tests/labelme_tests/dlcv_tests/test_copy_paste_gherkin.py`

## 新功能怎么开干

1. 抽出纯函数（坐标、config、文件、导入扫描），Qt 只接线。
2. 先写 `tests/features/*.feature` 用户可见场景（2～3 条），再写单测边界。
3. 红 → 实现到绿 → coverage 门槛 → 只对纯函数跑 cosmic-ray。
4. 人只看失败、覆盖洞、活变异体；GUI 主路径点一次。
5. 沉淀到 `.agent/`。

## 不要做

- 用长 `claude.md` / 堆砌规则代替测试（模型当建议，中间会丢）。
- 一次写完大规格再一次性实现（本仓库不要 SDD/瀑布）。
- 对 Qt widget / `app.py` 跑变异测试。
- 把人类 TDD「一行测一行代码」强加给 agent；要的是测得住、门禁在，不规定 agent 先测后码的节奏。
