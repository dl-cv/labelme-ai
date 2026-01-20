"""
UI 主题管理器（独立组件）

目标：
- 主题切换逻辑全部集中在这里：应用/恢复 QSS、同步控件布局、Dock 标题栏修复等
- `dlcv/app.py` 只负责创建管理器并调用 `set_theme/apply_from_settings` 等接口
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from qtpy import QtCore, QtWidgets
from qtpy.QtCore import Qt

from labelme.dlcv.dlcv_translator import dlcv_tr
from labelme.dlcv.ui_style import get_dlcv_modern_light_qss
from labelme.dlcv.utils_func import notification
from labelme.utils import logger

try:
    from pyqttoast import ToastPreset
except Exception:  # pragma: no cover
    ToastPreset = None  # type: ignore


class UiThemeManager:
    """管理 DLCV UI 主题（modern / classic）。

    说明：
    - 仅调整“外观”，不改变业务功能。
    - 默认 classic；若 settings 中保存为 modern，则启动即应用 modern。
    """

    THEME_MODERN = "modern"
    THEME_CLASSIC = "classic"
    _VALID_THEMES = (THEME_MODERN, THEME_CLASSIC)

    def __init__(self, main_window: QtWidgets.QMainWindow, settings: QtCore.QSettings):
        self.main_window = main_window
        self.settings = settings

        self.current_theme: Optional[str] = None

        self._original_ui_style_backup: Optional[Dict[str, Any]] = None
        self._original_tools_icon_size = None
        self._original_tools_button_style = None
        self._original_tools_layout: Optional[Dict[str, Any]] = None
        self._original_file_tree_indentation: Optional[int] = None

        # theme menu handle (optional)
        self._theme_menu: Optional[QtWidgets.QMenu] = None
        self._theme_action_group: Optional[QtWidgets.QActionGroup] = None
        self._action_modern: Optional[QtWidgets.QAction] = None
        self._action_classic: Optional[QtWidgets.QAction] = None

    # -------------------- Public API --------------------
    def get_saved_theme(self, default: str = THEME_CLASSIC) -> str:
        try:
            theme = self.settings.value("ui/theme", default)
        except Exception:
            theme = default
        theme = (theme or default).strip().lower()
        return theme if theme in self._VALID_THEMES else default

    def apply_from_settings(self) -> None:
        """启动时调用：按 settings 应用主题（默认 classic）。"""
        self.set_theme(self.get_saved_theme(default=self.THEME_CLASSIC), persist=False, notify=False)

    def install_to_setting_menu(self, setting_menu: QtWidgets.QMenu) -> QtWidgets.QMenu:
        """把“界面风格”子菜单安装到系统设置菜单里（可重复调用，幂等）。"""
        if self._theme_menu is not None:
            self._sync_menu_checked_state()
            return self._theme_menu

        theme_menu = setting_menu.addMenu(dlcv_tr("界面风格(UI Theme)"))
        self._theme_menu = theme_menu

        group = QtWidgets.QActionGroup(self.main_window)
        group.setExclusive(True)
        self._theme_action_group = group

        act_modern = QtWidgets.QAction(dlcv_tr("新版UI(现代)"), self.main_window)
        act_modern.setCheckable(True)
        act_modern.setData(self.THEME_MODERN)

        act_classic = QtWidgets.QAction(dlcv_tr("原版UI(恢复CSS)"), self.main_window)
        act_classic.setCheckable(True)
        act_classic.setData(self.THEME_CLASSIC)

        self._action_modern = act_modern
        self._action_classic = act_classic

        group.addAction(act_modern)
        group.addAction(act_classic)
        theme_menu.addAction(act_modern)
        theme_menu.addAction(act_classic)

        group.triggered.connect(lambda act: self.set_theme(str(act.data()), persist=True, notify=True))

        self._sync_menu_checked_state()
        return theme_menu

    def set_theme(self, theme: str, persist: bool = True, notify: bool = True) -> None:
        """切换主题（即时生效）。theme: 'modern' | 'classic'"""
        theme = (theme or self.THEME_CLASSIC).strip().lower()
        if theme not in self._VALID_THEMES:
            theme = self.THEME_CLASSIC

        self._ensure_original_ui_style_backup()
        self.current_theme = theme

        # 1) 应用/恢复 QSS + Qt Style
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                # 保留当前应用字体（避免切换主题时把字号设置“冲掉”）
                try:
                    current_font = app.font()
                except Exception:
                    current_font = None

                if theme == self.THEME_MODERN:
                    # Fusion 更接近截图观感，且跨平台一致
                    try:
                        app.setStyle("Fusion")
                    except Exception:
                        pass
                    app.setStyleSheet(get_dlcv_modern_light_qss())
                else:
                    # 原版：恢复启动时样式（或至少清空 QSS）
                    try:
                        style_name = (self._original_ui_style_backup or {}).get("qt_style")
                        if style_name:
                            app.setStyle(style_name)
                    except Exception:
                        pass
                    try:
                        original_sheet = (self._original_ui_style_backup or {}).get("style_sheet", "")
                        app.setStyleSheet(original_sheet or "")
                    except Exception:
                        app.setStyleSheet("")

                # 恢复字体（重要：新版 QSS 下字号修改需要稳定生效）
                if current_font is not None:
                    try:
                        app.setFont(current_font)
                    except Exception:
                        pass
        except Exception:
            logger.error("set_theme failed:\n%s", traceback_format())

        # 2) 同步控件“布局风格参数”（边距/按钮布局），保证两套风格切换一致
        try:
            self._apply_theme_widget_tweaks(theme)
        except Exception:
            logger.error("apply_theme_widget_tweaks failed:\n%s", traceback_format())

        # 3) 记录设置
        if persist:
            try:
                self.settings.setValue("ui/theme", theme)
            except Exception:
                pass

        # 4) 更新菜单勾选
        self._sync_menu_checked_state()

        # 5) 反馈
        if notify:
            try:
                msg = (
                    dlcv_tr("已切换为新版界面")
                    if theme == self.THEME_MODERN
                    else dlcv_tr("已恢复为原版界面")
                )
                if ToastPreset is not None:
                    notification(dlcv_tr("界面风格"), msg, ToastPreset.SUCCESS, 2500)
            except Exception:
                pass

    def on_app_font_changed(self) -> None:
        """当应用字体被修改（字号改变）后调用，用于新版主题下强制刷新与重算 Dock 标题栏高度。"""
        theme = self.current_theme or self.get_saved_theme(default=self.THEME_CLASSIC)
        if theme != self.THEME_MODERN:
            return
        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                current_sheet = app.styleSheet() or ""
                # 通过“清空再恢复”触发全量 repolish，确保字号多次修改也生效
                app.setStyleSheet("")
                app.setStyleSheet(current_sheet)
            except Exception:
                pass

        # 同时重算 dock 标题栏高度（自定义 titleBarWidget）
        try:
            self._apply_theme_widget_tweaks(self.THEME_MODERN)
        except Exception:
            pass

    # -------------------- Internals --------------------
    def _ensure_original_ui_style_backup(self) -> None:
        """备份原始 UI 样式，用于从新版 UI 一键恢复到原版。"""
        if self._original_ui_style_backup is not None:
            return
        app = QtWidgets.QApplication.instance()
        style_name = None
        style_sheet = ""
        try:
            if app is not None:
                try:
                    style_name = app.style().objectName()
                except Exception:
                    style_name = None
                try:
                    style_sheet = app.styleSheet() or ""
                except Exception:
                    style_sheet = ""
        except Exception:
            pass
        self._original_ui_style_backup = {"qt_style": style_name, "style_sheet": style_sheet}

        # Tools 工具栏原始参数（用于还原）
        try:
            tools = getattr(self.main_window, "tools", None)
            if tools is not None:
                self._original_tools_icon_size = tools.iconSize()
                self._original_tools_button_style = tools.toolButtonStyle()
                layout = tools.layout()
                if layout is not None:
                    m = layout.contentsMargins()
                    self._original_tools_layout = {
                        "spacing": layout.spacing(),
                        "margins": (m.left(), m.top(), m.right(), m.bottom()),
                    }
        except Exception:
            self._original_tools_icon_size = None
            self._original_tools_button_style = None
            self._original_tools_layout = None

    def _sync_menu_checked_state(self) -> None:
        if self._action_modern is None or self._action_classic is None:
            return
        theme = self.current_theme or self.get_saved_theme(default=self.THEME_CLASSIC)
        try:
            if theme == self.THEME_CLASSIC:
                self._action_classic.setChecked(True)
            else:
                self._action_modern.setChecked(True)
        except Exception:
            pass

    def _apply_theme_widget_tweaks(self, theme: str) -> None:
        """仅调整与主题相关的控件属性/间距（不影响功能）。"""
        is_modern = theme == self.THEME_MODERN
        mw = self.main_window

        # Tools 工具栏：按钮布局/间距/图标尺寸
        try:
            tools = getattr(mw, "tools", None)
            if tools is not None:
                btn_style = Qt.ToolButtonTextBesideIcon if is_modern else Qt.ToolButtonTextUnderIcon
                try:
                    tools.setToolButtonStyle(btn_style)
                except Exception:
                    pass

                # 同步已创建的按钮（ToolBar 会包装成 QToolButton）
                for btn in tools.findChildren(QtWidgets.QToolButton):
                    try:
                        btn.setToolButtonStyle(btn_style)
                    except Exception:
                        pass

                # 图标尺寸：现代固定 16；原版恢复备份
                try:
                    if is_modern:
                        tools.setIconSize(QtCore.QSize(16, 16))
                    else:
                        if self._original_tools_icon_size is not None:
                            tools.setIconSize(self._original_tools_icon_size)
                except Exception:
                    pass

                layout = tools.layout()
                if layout is not None:
                    if is_modern:
                        # 现代风格：整体更紧凑，减少工具栏高度/留白
                        layout.setSpacing(8)
                        layout.setContentsMargins(8, 6, 8, 6)
                        tools.setContentsMargins(8, 6, 8, 6)
                    else:
                        spacing = 0
                        margins = (0, 0, 0, 0)
                        orig = self._original_tools_layout
                        if isinstance(orig, dict):
                            spacing = orig.get("spacing", 0)
                            margins = orig.get("margins", (0, 0, 0, 0))
                        layout.setSpacing(spacing)
                        layout.setContentsMargins(*margins)
                        try:
                            tools.setContentsMargins(*margins)
                        except Exception:
                            pass
        except Exception:
            logger.error("tools tweak failed:\n%s", traceback_format())

        # 左侧文件列表：搜索框 + 树的内边距/占位文本/清除按钮
        try:
            w = getattr(mw, "fileListWidget", None)
            if w is not None and hasattr(w, "search_box") and hasattr(w, "layout"):
                if is_modern:
                    w.layout.setContentsMargins(8, 8, 8, 8)
                    w.layout.setSpacing(8)
                    w.search_box.setClearButtonEnabled(True)
                    w.search_box.setPlaceholderText(dlcv_tr("搜索文件名"))
                else:
                    w.layout.setContentsMargins(0, 0, 0, 0)
                    w.layout.setSpacing(0)
                    w.search_box.setClearButtonEnabled(False)
                    w.search_box.setPlaceholderText(dlcv_tr("输入关键字过滤 - Enter键搜索"))

                # 文件树缩进：现代风格缩进过长，改为原来的一半；切回 classic 恢复原值
                tree = getattr(w, "tree_widget", None)
                if tree is not None:
                    if self._original_file_tree_indentation is None:
                        try:
                            self._original_file_tree_indentation = int(tree.indentation())
                        except Exception:
                            self._original_file_tree_indentation = None

                    if self._original_file_tree_indentation is not None:
                        try:
                            if is_modern:
                                tree.setIndentation(max(8, self._original_file_tree_indentation // 2))
                            else:
                                tree.setIndentation(self._original_file_tree_indentation)
                        except Exception:
                            pass
        except Exception:
            logger.error("file list tweak failed:\n%s", traceback_format())

        # 右侧统计面板：布局边距/间距
        try:
            dock = getattr(mw, "label_count_dock", None)
            if dock is not None:
                widget = dock.widget()
                layout = widget.layout() if widget is not None else None
                if layout is not None:
                    if is_modern:
                        layout.setContentsMargins(8, 8, 8, 8)
                        layout.setSpacing(8)
                    else:
                        layout.setContentsMargins(0, 0, 0, 0)
                        layout.setSpacing(0)
        except Exception:
            logger.error("label_count_dock tweak failed:\n%s", traceback_format())

        # 右侧设置面板：容器边距（原版为 0）
        try:
            dock = getattr(mw, "setting_dock", None)
            if dock is not None:
                widget = dock.widget()
                layout = widget.layout() if widget is not None else None
                if layout is not None:
                    if is_modern:
                        layout.setContentsMargins(8, 8, 8, 8)
                        layout.setSpacing(6)
                    else:
                        layout.setContentsMargins(0, 0, 0, 0)
                        layout.setSpacing(6)
        except Exception:
            logger.error("setting_dock tweak failed:\n%s", traceback_format())

        # Dock 标题栏：新版 UI 使用自定义 titleBarWidget，彻底避免小字号（8/10）被裁切
        self._apply_modern_dock_title_bars(enable=is_modern)

    def _apply_modern_dock_title_bars(self, enable: bool) -> None:
        mw = self.main_window
        docks = []
        for name in ("file_dock", "setting_dock", "label_count_dock"):
            dock = getattr(mw, name, None)
            if dock is not None:
                docks.append(dock)

        for dock in docks:
            if enable:
                self._set_dock_custom_title_bar(dock)
            else:
                self._unset_dock_custom_title_bar(dock)

    def _unset_dock_custom_title_bar(self, dock: QtWidgets.QDockWidget) -> None:
        tb = dock.titleBarWidget()
        if tb is None:
            return
        if getattr(tb, "objectName", lambda: "")() != "dlcvDockTitleBar":
            return
        try:
            dock.setTitleBarWidget(None)  # 恢复 Qt 默认标题栏
        except Exception:
            return
        try:
            tb.deleteLater()
        except Exception:
            pass

    def _set_dock_custom_title_bar(self, dock: QtWidgets.QDockWidget) -> None:
        # 已设置过则只更新文本/高度
        tb = dock.titleBarWidget()
        if tb is not None and tb.objectName() == "dlcvDockTitleBar":
            label = tb.findChild(QtWidgets.QLabel, "dlcvDockTitleLabel")
            if label is not None:
                label.setText(dock.windowTitle())
                self._update_dock_title_bar_height(tb, label)
            return

        title_bar = QtWidgets.QWidget(dock)
        title_bar.setObjectName("dlcvDockTitleBar")
        layout = QtWidgets.QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(6)

        label = QtWidgets.QLabel(dock.windowTitle(), title_bar)
        label.setObjectName("dlcvDockTitleLabel")
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(label, 1)

        # float 按钮（如果允许）
        if dock.features() & QtWidgets.QDockWidget.DockWidgetFloatable:
            float_btn = QtWidgets.QToolButton(title_bar)
            float_btn.setObjectName("dlcvDockTitleBtn")
            float_btn.setAutoRaise(True)
            float_btn.setCheckable(True)
            float_btn.setChecked(dock.isFloating())

            def _sync_float_btn() -> None:
                try:
                    float_btn.setChecked(dock.isFloating())
                    icon = dock.style().standardIcon(
                        QtWidgets.QStyle.SP_TitleBarNormalButton
                        if dock.isFloating()
                        else QtWidgets.QStyle.SP_TitleBarMaxButton
                    )
                    float_btn.setIcon(icon)
                except Exception:
                    pass

            _sync_float_btn()
            float_btn.clicked.connect(lambda checked, d=dock: d.setFloating(checked))
            try:
                dock.topLevelChanged.connect(lambda _: _sync_float_btn())
            except Exception:
                pass
            layout.addWidget(float_btn)

        # close 按钮（如果允许）
        if dock.features() & QtWidgets.QDockWidget.DockWidgetClosable:
            close_btn = QtWidgets.QToolButton(title_bar)
            close_btn.setObjectName("dlcvDockTitleBtn")
            close_btn.setAutoRaise(True)
            try:
                close_btn.setIcon(dock.style().standardIcon(QtWidgets.QStyle.SP_TitleBarCloseButton))
            except Exception:
                pass
            close_btn.clicked.connect(dock.close)
            layout.addWidget(close_btn)

        dock.setTitleBarWidget(title_bar)

        # 标题变化时同步
        try:
            dock.windowTitleChanged.connect(label.setText)
        except Exception:
            pass

        self._update_dock_title_bar_height(title_bar, label)

    def _update_dock_title_bar_height(self, title_bar: QtWidgets.QWidget, label: QtWidgets.QLabel) -> None:
        # 关键：用 fontMetrics 精确算高度，确保 8/10 号字也不会被裁切
        try:
            fm = label.fontMetrics()
            h = int(fm.height()) + 12
            h = max(28, h)
            title_bar.setFixedHeight(h)
        except Exception:
            pass


def traceback_format() -> str:
    import traceback

    return traceback.format_exc()

