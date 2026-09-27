"""Cajas delatoras: utilidades geométricas (IoU) y Non-Maximum Suppression.

NMS puro NumPy: la salida cruda de SCRFD trae miles de candidatos solapados
por nivel de la pirámide FPN; esta capa deja una caja por rostro.
"""
import numpy as np


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU por pares entre dos lotes de cajas xyxy → matriz (len(a), len(b))."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    a_ = a[:, None, :4].astype(np.float32)  # (Na, 1, 4)
    b_ = b[None, :, :4].astype(np.float32)  # (1, Nb, 4)
    inter_w = np.maximum(0.0, np.minimum(a_[..., 2], b_[..., 2]) - np.maximum(a_[..., 0], b_[..., 0]))
    inter_h = np.maximum(0.0, np.minimum(a_[..., 3], b_[..., 3]) - np.maximum(a_[..., 1], b_[..., 1]))
    inter = inter_w * inter_h
    area_a = (a_[..., 2] - a_[..., 0]) * (a_[..., 3] - a_[..., 1])
    area_b = (b_[..., 2] - b_[..., 0]) * (b_[..., 3] - b_[..., 1])
    union = area_a + area_b - inter
    return (inter / np.maximum(union, 1e-9)).astype(np.float32)


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.4) -> list[int]:
    """Non-Maximum Suppression greedy. Devuelve los índices que sobreviven.

    ``boxes``: (N, 4) xyxy; ``scores``: (N,). Determinista: desempata por índice.
    """
    if len(boxes) == 0:
        return []
    order = np.argsort(-scores, kind="stable")
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        ious = iou_matrix(boxes[i : i + 1], boxes[rest])[0]
        order = rest[ious <= iou_threshold]
    return keep
