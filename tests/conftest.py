"""测试采集前打补丁：避免 labelme.__init__ 拉 imgviz/cv2。"""
import sys
import types


def _stub_labelme_testing():
    if "labelme.testing" in sys.modules:
        return
    mod = types.ModuleType("labelme.testing")

    def assert_labelfile_sanity(*_args, **_kwargs):
        return None

    mod.assert_labelfile_sanity = assert_labelfile_sanity
    sys.modules["labelme.testing"] = mod


def _patch_cv2_dictvalue():
    try:
        import cv2

        dnn = getattr(cv2, "dnn", None)
        if dnn is not None and not hasattr(dnn, "DictValue"):

            class DictValue:
                def __init__(self, *args, **kwargs):
                    pass

            dnn.DictValue = DictValue
    except Exception:
        pass


_stub_labelme_testing()
_patch_cv2_dictvalue()
