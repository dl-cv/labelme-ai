from labelme.ai import *
from labelme.dlcv.ai.efficient_sam import EfficientSam


class EfficientSamVitS(EfficientSam):
    name = "EfficientSam (accuracy)"

    def __init__(self):
        super().__init__(
            encoder_path='C:/dlcv/bin/efficient_sam_vits_encoder.onnx',
            decoder_path='C:/dlcv/bin/efficient_sam_vits_decoder.onnx',
        )


MODELS = [
    EfficientSamVitS,
]
