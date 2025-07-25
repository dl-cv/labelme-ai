import json
import time
from typing import List, Tuple

import numpy as np

from labelme.logger import logger


def get_rectangles_from_texts(
        model: str, image: np.ndarray, texts: List[str]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    import osam

    request: osam.types.GenerateRequest = osam.types.GenerateRequest(
        model=model,
        image=image,
        prompt=osam.types.Prompt(
            texts=texts,
            iou_threshold=1.0,
            score_threshold=0.01,
            max_annotations=1000,
        ),
    )
    logger.debug(
        f"Requesting with model={model!r}, image={(image.shape, image.dtype)}, "
        f"prompt={request.prompt!r}"
    )
    t_start = time.time()
    response: osam.types.GenerateResponse = osam.apis.generate(request=request)

    num_annotations = len(response.annotations)
    logger.debug(
        f"Response: num_annotations={num_annotations}, "
        f"elapsed_time={time.time() - t_start:.3f} [s]"
    )

    boxes: np.ndarray = np.empty((num_annotations, 4), dtype=np.float32)
    scores: np.ndarray = np.empty((num_annotations,), dtype=np.float32)
    labels: np.ndarray = np.empty((num_annotations,), dtype=np.int32)
    for i, annotation in enumerate(response.annotations):
        boxes[i] = [
            annotation.bounding_box.xmin,
            annotation.bounding_box.ymin,
            annotation.bounding_box.xmax,
            annotation.bounding_box.ymax,
        ]
        scores[i] = annotation.score
        labels[i] = texts.index(annotation.text)

    return boxes, scores, labels


def non_maximum_suppression(
        boxes: np.ndarray,
        scores: np.ndarray,
        labels: np.ndarray,
        iou_threshold: float,
        score_threshold: float,
        max_num_detections: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    import osam

    num_classes = np.max(labels) + 1
    scores_of_all_classes = np.zeros((len(boxes), num_classes), dtype=np.float32)
    for i, (score, label) in enumerate(zip(scores, labels)):
        scores_of_all_classes[i, label] = score
    logger.debug(f"Input: num_boxes={len(boxes)}")
    boxes, scores, labels = osam.apis.non_maximum_suppression(
        boxes=boxes,
        scores=scores_of_all_classes,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        max_num_detections=max_num_detections,
    )
    logger.debug(f"Output: num_boxes={len(boxes)}")
    return boxes, scores, labels


def get_shapes_from_annotations(
        boxes: np.ndarray, scores: np.ndarray, labels: np.ndarray, texts: List[str]
) -> List[dict]:
    shapes: List[dict] = []
    for box, score, label in zip(boxes.tolist(), scores.tolist(), labels.tolist()):
        text = texts[label]
        xmin, ymin, xmax, ymax = box
        shape = {
            "label": text,
            "points": [[xmin, ymin], [xmax, ymax]],
            "group_id": None,
            "shape_type": "rectangle",
            "flags": {},
            "description": json.dumps(dict(score=score, text=text)),
        }
        shapes.append(shape)
    return shapes
