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
    /* 现代风格工具栏：整体更紧凑 */
    padding: 6px 8px;
}}
QToolBar#ToolsToolBar::separator {{
    /* 分隔符不要用背景色“铺满”，否则在某些 Style/缩放下会变成一整条粗灰块 */
    background: transparent;
    /* 注意：width 在部分 Style 下可能不生效，因此线条用 border 来保证永远是 1px */
    width: 1px;
    margin: 6px 8px;
}}
QToolBar#ToolsToolBar::separator:horizontal {{
    border-left: 1px solid #E5E7EB;
}}
QToolBar#ToolsToolBar::separator:vertical {{
    border-top: 1px solid #E5E7EB;
}}
QToolBar#ToolsToolBar QToolButton {{
    background: #FFFFFF;
    border: 1px solid #D6DAE3;
    border-radius: 6px;
    /* 1) 减少高度/内边距 2) 缩小图标与文字区域的留白 */
    /* 右侧再收紧一点，避免“文字右侧空一截”的观感 */
    padding: 4px -15px 4px 6px;
    color: #111827;
    min-height: 35px;
    margin: 0px;
}}
/* 若某些 ToolButton 绑定了 menu，会预留 indicator 空间；这里把它收紧 */
QToolBar#ToolsToolBar QToolButton::menu-indicator {{
    image: none;
    width: 0px;
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
    /* 兼容大字号：避免标题文字被裁切 */
    min-height: 30px;
    /* 小字号更容易被 padding 顶掉可用高度，缩小上下 padding */
    padding: 3px 10px;
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
    /* 让选中高亮覆盖整行（含 checkbox/缩进），避免“选中项右移”的观感 */
    show-decoration-selected: 1;
}}
QTreeWidget#fileTree::item {{
    /* 左侧文件列表：行距尽量贴近原版 */
    padding: 2px 6px;
    color: #111827;
}}
QTreeWidget#fileTree::item:selected,
QTreeWidget#fileTree::item:selected:active,
QTreeWidget#fileTree::item:selected:!active {{
    /* 选中态：跟随系统高亮，更接近原版表现 */
    background: palette(highlight);
    color: palette(highlighted-text);
    /* 明确指定，避免某些平台/Style 下选中态 padding 变化导致位移 */
    padding: 2px 6px;
    margin: 0px;
}}

/* 关键：缩进/分支区域由 branch 子控件绘制，选中时也一起涂底色，避免“选中行从文字处才开始变色” */
QTreeWidget#fileTree::branch:selected,
QTreeWidget#fileTree::branch:selected:active,
QTreeWidget#fileTree::branch:selected:!active {{
    background: palette(highlight);
}}

/* 固定 item view 里的复选框尺寸/边距，避免选中态导致文本视觉位移 */
QTreeWidget#fileTree::indicator {{
    width: 14px;
    height: 14px;
    margin: 0px 6px 0px 2px;
    /* 现代风格下（Fusion）默认复选框会带圆角，这里强制画成正方形 */
    border: 1px solid #D1D5DB;
    border-radius: 0px;
    background: #FFFFFF;
}}

QTreeWidget#fileTree::indicator:unchecked:hover {{
    border-color: {accent};
}}

QTreeWidget#fileTree::indicator:checked {{
    /* 用资源里的 done.png 作为对勾，避免依赖平台默认绘制 */
    image: url(:/done.png);
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
    /* 兼容大字号：避免标题文字被裁切 */
    min-height: 30px;
    /* 小字号更容易被 padding 顶掉可用高度，缩小上下 padding */
    padding: 3px 10px;
    border-bottom: 1px solid #E5E7EB;
    font-weight: 600;
}}

/* 自定义 Dock 标题栏（用于彻底解决 8/10 号字裁切问题） */
QWidget#dlcvDockTitleBar {{
    background: #F9FAFB;
    border-bottom: 1px solid #E5E7EB;
}}
QLabel#dlcvDockTitleLabel {{
    color: #111827;
    font-weight: 600;
}}
QToolButton#dlcvDockTitleBtn {{
    border: none;
    background: transparent;
    padding: 4px;
    border-radius: 6px;
}}
QToolButton#dlcvDockTitleBtn:hover {{
    background: #F3F4F6;
}}
QToolButton#dlcvDockTitleBtn:pressed {{
    background: #E8F0FF;
}}

/* -------------------- Right Docks: Lists (Label/Polygon/Flags) -------------------- */
QDockWidget#Flags,
QDockWidget#Labels,
QDockWidget[objectName="Label List"] {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
}}

QDockWidget#Flags QListWidget,
QDockWidget#Labels QListView,
QDockWidget[objectName="Label List"] QListWidget {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    outline: none;
    padding: 4px;
}}

QDockWidget#Flags QListWidget::item,
QDockWidget#Labels QListView::item,
QDockWidget[objectName="Label List"] QListWidget::item {{
    padding: 2px 6px;
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

