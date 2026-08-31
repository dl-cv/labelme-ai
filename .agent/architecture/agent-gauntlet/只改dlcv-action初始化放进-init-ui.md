# 只改 dlcv；action 改动放进 `_init_ui`

本仓库真正产品代码在 `labelme/dlcv/`。`labelme/app.py`、`labelme/widgets/`、`labelme/config/` 是旧版 labelme 上游，**不要为产品需求去改那些文件**。

覆盖方式：dlcv `MainWindow(CopyPasteMixin, 上游 MainWindow)`，在 dlcv 里 override / mixin / 摘 action。

## QAction 约定

新增、改文案、`setEnabled`、隐藏、从菜单/工具栏/右键摘掉、清 shortcut、以及 `_init_edit_mode_action` 这类初始化：

- 写在 `labelme/dlcv/app.py` 的 `_init_ui`
- 或 `_init_ui` 调用的 `_init_trigger_action` / `_init_edit_mode_action`
- **不要**写在 `MainWindow.__init__` 里（`__init__` 只调 `_init_ui()`）

上游还在创建、但产品已弃用的 action（例如 Duplicate / Ctrl+D）：

1. 从 `self.actions.tool` / `menu` / `editMenu` 元组里滤掉
2. `removeAction` 编辑菜单、画布右键、`self.tools`
3. `setVisible(False)`、`setEnabled(False)`、`setShortcut("")`
4. **不要再调 `populateModeActions()`**。dlcv 覆盖里会 `tool[1:]` 去掉「打开文件」；第二次调用会把已经排在第一位的「打开目录」也切掉。只 `removeAction` 当前菜单/工具栏即可。

Ctrl+Shift+V 这类产品不要的快捷键：不要在 `_init_ui` 里注册；不要改上游去删槽函数。
