from qtpy import QtCore

from labelme.ai.efficient_sam import *
from labelme.dlcv.dlcv_translator import DlcvTrObject
from labelme.dlcv.utils_func import notification
import pynvml


# 注意这里的继承顺序, DlcvTrObject 在前, QtCore.QObject 在后,这样使用的 self.tr 为 DlcvTrObject 的 tr
class EfficientSam(EfficientSam, DlcvTrObject, QtCore.QObject):
    sig_start = QtCore.Signal()
    sig_done = QtCore.Signal()

    def __init__(self, encoder_path, decoder_path, parent=None):
        # super().__init__(encoder_path, decoder_path)

        # 查看显卡驱动版本
        support_gpu = False

        try:
            pynvml.nvmlInit()
            driver_version = pynvml.nvmlSystemGetDriverVersion()
            print(f"Driver Version: {driver_version}")
            pynvml.nvmlShutdown()
            version = int(driver_version.split('.')[0])
            if version >= 531:
                support_gpu = True
            else:
                from qtpy.QtWidgets import QMessageBox
                QMessageBox.warning(
                    None, "提示",
                    f"显卡驱动版本过低, 当前版本：{version}，请升级显卡驱动版本至532以上，以支持GPU加速AI标注。")
        except:
            pass

        if support_gpu:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        else:
            providers = ['CPUExecutionProvider']
        self._encoder_session = onnxruntime.InferenceSession(
            encoder_path, providers=providers)
        self._decoder_session = onnxruntime.InferenceSession(
            decoder_path, providers=providers)
        self._lock = threading.Lock()
        self._image_embedding_cache = collections.OrderedDict()
        self._thread = None

        super(QtCore.QObject, self).__init__(parent)

        self.sig_start.connect(self.start)
        self.sig_done.connect(self.done)

    def start(self):
        notification(self.tr("ai processing..."))

    def done(self):
        notification(self.tr("ai process done"))

    def _compute_and_cache_image_embedding(self):
        # 通知
        self.sig_start.emit()

        super()._compute_and_cache_image_embedding()

        # 结束通知
        self.sig_done.emit()
