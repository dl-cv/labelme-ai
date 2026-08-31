# agent-gauntlet

本 Qt/labelme 项目里，coding agent 怎么干活、什么算做完。

一句话：Agent 写代码可以快；人信的是 `make` 门禁，不是自己把 `app.py` 读一遍。只对**抽得出纯函数、测得住**的模块成立。画布、快捷键、闪退仍要人碰。

## 子文档

- [为什么不靠长提示词而靠测试和变异测试.md](为什么不靠长提示词而靠测试和变异测试.md)
- [新功能怎么套复制粘贴那套门禁.md](新功能怎么套复制粘贴那套门禁.md)
- [只改dlcv-action初始化放进-init-ui.md](只改dlcv-action初始化放进-init-ui.md)

## 涉及文件

- `AGENTS.md` — 短规则 + 命令
- `Makefile` — `test-copy-paste` / `coverage-copy-paste` / `mutate-copy-paste` / `qa-copy-paste`
- `docs/qa/copy-paste-quality-metrics.md` — 复制粘贴阈值
- `tests/features/` — Gherkin
- `tools/qa_copy_paste.py`、`tools/cosmic-ray-copy-paste.toml`

## 和人的分工

| 角色 | 做 | 不做 |
| --- | --- | --- |
| 人 | 场景对不对、模块边界、门槛数字、Qt 点主路径 | 逐行审 `clip_paste` 一类纯函数 |
| Agent | 实现到绿、补测、过 ruff | 没有门禁就宣称「Qt 功能完成」 |
