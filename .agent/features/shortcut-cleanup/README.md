# 工具栏 mnemonic 清理

去掉上游翻译文本中的 mnemonic 标记，避免工具栏 action 显示多余的 `(D)`、`(B)`。

## 涉及文件

- `labelme/dlcv/app.py` — 在 `_init_ui` 中覆盖 `deleteFile` 和 `brightnessContrast` 的 `text/iconText`，去掉 `(&D)`、`(&B)` 标记。

## 为什么必须这样

上游 action 文本包含 `删除(&D)`、`亮度 对比度(&B)`。Qt 会把 mnemonic 渲染成工具栏文字后的 `(D)`、`(B)`；清理显示文本即可，不需要修改 action 的实际 shortcut。
