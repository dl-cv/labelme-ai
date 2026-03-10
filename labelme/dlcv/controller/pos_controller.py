from PyQt5 import QtWidgets


def ensure_window_in_screen(window: QtWidgets.QMainWindow):
    """
    确保窗口位置没有超出屏幕。
    如果窗口越界（位置小于0、超出屏幕边界，或窗口大小超过屏幕），
    则重置为默认位置 (0, 0) 和大小 800x600。

    Args:
        window: QtWidgets.QWidget 或其子类实例
    """
    if hasattr(QtWidgets.QApplication, "primaryScreen"):
        screen = QtWidgets.QApplication.primaryScreen()
    else:
        screen = QtWidgets.QDesktopWidget().screen()

    if screen is not None:
        screen_geometry = screen.geometry()
        current_geometry = window.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # 检查是否越界：窗口位置或大小超出屏幕范围
        is_out_of_bounds = (
            current_geometry.x() < 0
            or current_geometry.y() < 0
            or current_geometry.right() > screen_width
            or current_geometry.bottom() > screen_height
            or current_geometry.width() > screen_width
            or current_geometry.height() > screen_height
        )

        if is_out_of_bounds:
            # 越界则重置为默认位置和大小
            window.move(0, 0)
            window.resize(800, 600)
