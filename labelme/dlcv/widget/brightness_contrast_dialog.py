from qtpy import QtCore, QtGui, QtWidgets

from labelme.dlcv.store import STORE
from labelme.utils.image import numpy_to_qimage


class BrightnessContrastDialog(QtWidgets.QDialog):
    """亮度/对比度调节弹窗。

    调节时实时预览效果，关闭时保存到 STORE，
    切图时对每张图自动应用相同参数。
    """

    _base_value = 50

    def __init__(self, image, callback, parent=None):
        super(BrightnessContrastDialog, self).__init__(parent)
        self.setWindowTitle("Brightness/Contrast")
        self.setModal(True)
        self._image = image
        self._callback = callback

        # 初始值取全局设置（无记录时亮度对比度均为 1.0）
        brightness, contrast = STORE.brightness_contrast_values
        if brightness is None:
            brightness = 1.0
        if contrast is None:
            contrast = 1.0

        self._brightness = brightness
        self._contrast = contrast

        self.slider_brightness = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_contrast = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        for slider in (self.slider_brightness, self.slider_contrast):
            slider.setRange(0, 3 * self._base_value)
        self.slider_brightness.setValue(int(brightness * self._base_value))
        self.slider_contrast.setValue(int(contrast * self._base_value))

        self.label_brightness_value = QtWidgets.QLabel(
            f"{brightness:.2f}"
        )
        self.label_brightness_value.setAlignment(QtCore.Qt.AlignRight)
        self.label_contrast_value = QtWidgets.QLabel(f"{contrast:.2f}")
        self.label_contrast_value.setAlignment(QtCore.Qt.AlignRight)

        def _on_brightness(value):
            self._brightness = value / self._base_value
            self.label_brightness_value.setText(f"{self._brightness:.2f}")
            self.onNewValue()

        def _on_contrast(value):
            self._contrast = value / self._base_value
            self.label_contrast_value.setText(f"{self._contrast:.2f}")
            self.onNewValue()

        self.slider_brightness.valueChanged.connect(_on_brightness)
        self.slider_contrast.valueChanged.connect(_on_contrast)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(self._slider_row(
            self.tr("Brightness:"), self.slider_brightness, self.label_brightness_value
        ))
        layout.addLayout(self._slider_row(
            self.tr("Contrast:"), self.slider_contrast, self.label_contrast_value
        ))

        self._reset_button = QtWidgets.QPushButton(self.tr("Reset"))
        self._reset_button.clicked.connect(self._on_reset)
        layout.addWidget(self._reset_button)

        self.setLayout(layout)

    @staticmethod
    def _slider_row(title, slider, value_label):
        row = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel(title)
        title_label.setFixedWidth(75)
        row.addWidget(title_label)
        row.addWidget(slider)
        row.addWidget(value_label)
        return row

    def onNewValue(self):
        image = self._apply_adjust(self._image, self._brightness, self._contrast)
        self._callback(image)

    def _on_reset(self):
        self.slider_brightness.setValue(self._base_value)
        self.slider_contrast.setValue(self._base_value)
        self.onNewValue()

    def accept(self):
        # 关闭时把参数写入全局设置，保证后续切图都应用该效果
        self._save_to_store()
        super().accept()

    def reject(self):
        # 无确定/取消按钮，窗口关闭即视为确认，同样保存
        self._save_to_store()
        super().reject()

    def _save_to_store(self):
        STORE.brightness_contrast_values = (self._brightness, self._contrast)

    @staticmethod
    def _apply_adjust(image, brightness, contrast):
        import cv2
        import numpy as np

        array = np.asarray(image)
        img = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)

        if brightness != 1.0:
            img = cv2.convertScaleAbs(img, alpha=1.0, beta=(brightness - 1.0) * 255)
        if contrast != 1.0:
            img = cv2.convertScaleAbs(img, alpha=contrast, beta=0)

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return numpy_to_qimage(img)
