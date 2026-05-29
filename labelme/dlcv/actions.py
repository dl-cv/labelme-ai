from labelme.dlcv import dlcv_tr


def install_create_brush_mode_action(window, create_action):
    """Create and place the DLCV brush annotation action."""
    create_brush_mode = create_action(
        dlcv_tr("创建画笔"),
        lambda: window.toggleDrawMode(False, createMode="brush"),
        window._config["shortcuts"]["create_brush"],
        "objects",
        dlcv_tr("开始使用画笔绘制"),
        enabled=False,
    )
    create_brush_mode.setIconText(
        create_brush_mode.text() + f"({create_brush_mode.shortcut().toString()})"
    )
    window.actions.createBrushMode = create_brush_mode

    # 未加载图像时不可用；加载图像后随 toggleActions(True) 自动启用
    if hasattr(window.actions, "onLoadActive") and (
        window.actions.createBrushMode not in window.actions.onLoadActive
    ):
        window.actions.onLoadActive = tuple(window.actions.onLoadActive) + (
            window.actions.createBrushMode,
        )

    try:
        rotation_idx = window.actions.tool.index(window.actions.createRotationMode)
        window.actions.tool.insert(rotation_idx + 1, window.actions.createBrushMode)
    except ValueError:
        window.actions.tool.append(window.actions.createBrushMode)

    if window.actions.createBrushMode not in window.actions.menu:
        window.actions.menu = list(window.actions.menu)
        window.actions.menu.insert(3, window.actions.createBrushMode)

    return create_brush_mode
