"""
DLCV UI 主题样式（QSS）。

仅负责“外观”，不改变任何功能逻辑。
"""


def get_dlcv_modern_light_qss(accent: str = "#2F6FED") -> str:
    # 说明：
    # - 尽量“按控件 ID 精准命中”，避免影响 labelme 原有的 label 颜色展示等逻辑。
    # - 仍然对 QMenuBar/QMenu 做全局美化（较安全）。
    return f"""
/* -------------------- App Base -------------------- */
QMainWindow {{
    background: #F4F6FA;
}}

QStatusBar {{
    background: #FFFFFF;
    border-top: 1px solid #E5E7EB;
}}

/* -------------------- Menu Bar -------------------- */
QMenuBar {{
    background: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
    padding: 2px 6px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 10px;
    margin: 2px 2px;
    border-radius: 6px;
    color: #111827;
}}
QMenuBar::item:selected {{
    background: #F3F4F6;
}}
QMenuBar::item:pressed {{
    background: {accent};
    color: #FFFFFF;
}}

QMenu {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 12px;
    border-radius: 6px;
    color: #111827;
}}
QMenu::item:selected {{
    background: #F3F4F6;
}}
QMenu::separator {{
    height: 1px;
    background: #E5E7EB;
    margin: 6px 4px;
}}
QMenu::item:disabled {{
    color: #9CA3AF;
}}

/* -------------------- Tools Toolbar -------------------- */
QToolBar#ToolsToolBar {{
    background: #FFFFFF;
    border: 0px;
    padding: 6px 8px;
}}
QToolBar#ToolsToolBar::separator {{
    background: #E5E7EB;
    width: 1px;
    margin: 6px 8px;
}}
QToolBar#ToolsToolBar QToolButton {{
    background: #FFFFFF;
    border: 1px solid #D6DAE3;
    border-radius: 6px;
    padding: 6px 10px;
    color: #111827;
    min-height: 32px;
}}
QToolBar#ToolsToolBar QToolButton:hover {{
    background: #F3F4F6;
}}
QToolBar#ToolsToolBar QToolButton:pressed {{
    background: #E8F0FF;
    border-color: {accent};
}}
QToolBar#ToolsToolBar QToolButton:checked {{
    background: {accent};
    border-color: {accent};
    color: #FFFFFF;
}}
QToolBar#ToolsToolBar QToolButton:disabled {{
    color: #9CA3AF;
    border-color: #E5E7EB;
    background: #F9FAFB;
}}

/* -------------------- File List Dock (Left) -------------------- */
QDockWidget#Files {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
}}
QDockWidget#Files::title {{
    background: #F9FAFB;
    padding: 8px 10px;
    border-bottom: 1px solid #E5E7EB;
    font-weight: 600;
}}

QWidget#fileListPanel {{
    background: transparent;
}}
QLineEdit#fileSearch {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 30px;
    color: #111827;
    selection-background-color: #E8F0FF;
}}
QLineEdit#fileSearch:focus {{
    border-color: {accent};
}}

QTreeWidget#fileTree {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    outline: none;
}}
QTreeWidget#fileTree::item {{
    padding: 6px 8px;
    color: #111827;
}}
QTreeWidget#fileTree::item:selected {{
    background: #E8F0FF;
    color: #111827;
}}

/* -------------------- Right Panels: Stats + Settings -------------------- */
QDockWidget#label_count_dock,
QDockWidget#setting_dock {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
}}
QDockWidget#label_count_dock::title,
QDockWidget#setting_dock::title {{
    background: #F9FAFB;
    padding: 8px 10px;
    border-bottom: 1px solid #E5E7EB;
    font-weight: 600;
}}

QWidget#settingPanel {{
    background: transparent;
}}

QTreeWidget#settingParameterTree {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
}}

QTextEdit#labelCountText {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 6px 10px;
    color: #111827;
}}

QPushButton#labelCountBtn {{
    background: #FFFFFF;
    border: 1px solid #D6DAE3;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 32px;
    color: #111827;
}}
QPushButton#labelCountBtn:hover {{
    background: #F3F4F6;
}}
QPushButton#labelCountBtn:pressed {{
    background: #E8F0FF;
    border-color: {accent};
}}

/* -------------------- Scroll Bars (subtle) -------------------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #D1D5DB;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #9CA3AF;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #D1D5DB;
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #9CA3AF;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
"""

