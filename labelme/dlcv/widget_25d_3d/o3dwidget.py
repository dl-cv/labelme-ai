import sys

import cv2
from qtpy import QtWidgets, QtGui, QtCore


class InitFlagEnum:
    NOT_INIT = 0
    INITING = 1
    END = 2

    @staticmethod
    def is_initialized(value):
        return value == InitFlagEnum.END


class O3DWidget(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super(O3DWidget, self).__init__("3D视图", parent)

        # 属性
        self._init_flag = InitFlagEnum.NOT_INIT  # 如果改了文本，需要同步修改__getattribute__函数
        self.central_widget = None
        self.vis = None
        self.window = None
        self.window_container = None
        self.timer = None

    def __getattribute__(self, item):
        if item == "_init_flag" or item == 'show' or item == 'hide' or 'isVisible':
            return super().__getattribute__(item)

        if self._init_flag == InitFlagEnum.NOT_INIT:
            self._init_flag = InitFlagEnum.INITING
            self.__lazy_init()

        return super().__getattribute__(item)

    def __lazy_init(self):
        import open3d as o3d

        if InitFlagEnum.is_initialized(self._init_flag):
            return

        # 创建中心部件
        self.central_widget = QtWidgets.QWidget()
        self.setWidget(self.central_widget)
        layout = QtWidgets.QVBoxLayout(self.central_widget)

        # 初始化Open3D可视化器
        self.vis = o3d.visualization.Visualizer()
        self.vis.create_window(visible=False)  # 创建不可见的窗口

        # 获取窗口句柄并嵌入
        hwnd = self.__get_hwnd()
        self.window = QtGui.QWindow.fromWinId(hwnd)
        self.window_container = QtWidgets.QWidget.createWindowContainer(self.window, self.central_widget)
        layout.addWidget(self.window_container)

        # 设置定时器更新视图
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.__update_vis)
        self.timer.start(1)

        # 禁用默认的DockWidget功能
        self.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)

        self._init_flag = InitFlagEnum.END

    def display_with_path(self, gray_img_path, depth_img_path):
        from labelme.dlcv.utils_func import cv_imread

        gray_img = cv_imread(gray_img_path)
        depth_img = cv_imread(depth_img_path)
        self.display_with_array(gray_img, depth_img)

    def display_with_array(self, gray_img, depth_img):
        from labelme.dlcv.widget_25d_3d.utils import img2pcd

        # 清除之前的几何体
        self.vis.clear_geometries()
        # 添加新的点云
        pcd = img2pcd(gray_img, depth_img, 0.2)
        self.vis.add_geometry(pcd)
        # 重置视图
        self.vis.reset_view_point(True)

    def __get_hwnd(self):
        import win32gui
        hwnd = win32gui.FindWindowEx(0, 0, None, "Open3D")
        return hwnd

    def __update_vis(self):
        # print(self.vis.get_view_control().get_field_of_view())
        self.vis.get_view_control().change_field_of_view(
            -90)  # 设置正交视角，不知道为什么，只有在这里设置，才能生效 https://github.com/isl-org/Open3D/issues/2367
        self.vis.update_renderer()
        self.vis.poll_events()

    def closeEvent(self, event):
        if InitFlagEnum.is_initialized(self._init_flag):
            # 清理资源
            self.timer.stop()
            self.vis.destroy_window()
        super().closeEvent(event)


if __name__ == '__main__':
    from labelme.dlcv.widget_25d_3d.tests import gray_img_path, depth_img_path

    app = QtWidgets.QApplication(sys.argv)
    main_window = QtWidgets.QMainWindow()

    # 创建并添加dock widget
    o3d_widget = O3DWidget(main_window)
    main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, o3d_widget)

    # 显示测试数据
    o3d_widget.display_with_path(gray_img_path, depth_img_path)

    main_window.setWindowTitle('3D视图测试')
    main_window.setGeometry(100, 100, 800, 600)
    main_window.show()

    sys.exit(app.exec_())
