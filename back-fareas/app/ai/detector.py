"""Detector de rostros SCRFD (models/det_10g.onnx, pack buffalo_l).

Implementación directa sobre onnxruntime de la decodificación del paper
``Sample and Computation Redistribution for Efficient Face Detection``
(SCRFD): 3 niveles FPN (strides 8/16/32), 2 anclas por celda; la red predice
DISTANCIAS (l,t,r,b) desde el centro de cada ancla, ya multiplicadas por el
stride hay que decodificarlas a cajas xyxy. Los 5 landmarks salen igual
(distancia desde el centro) y son los que usa el embedder para alinear.

Pre-procesado estilo insightface: RGB, 640x640, (pixel - mean) / std.
Los dos detalles que hay que calibrar empíricamente (la exportación oficial
no lo documenta): la normalización y si la salida de score ya trae sigmoide.
Ambos se validaron contra el video real de prueba; ver notas en README.
"""
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from app.ai.boxes import nms

# Normalización del detector det_10g (misma familia que ArcFace: centrado en 127.5).
DET_MEAN = 127.5
DET_STD = 128.0

STRIDES = (8, 16, 32)
NUM_ANCHORS = 2  # anclas por celda en los modelos 10G


@dataclass(frozen=True)
class Face:
    """Rostro detectado en coordenadas del frame ORIGINAL."""

    box: np.ndarray  # (4,) x1,y1,x2,y2
    score: float  # confianza 0..1
    kps: np.ndarray  # (5,2) ojos, nariz, comisuras - para alinear


class ScrfdDetector:
    """Detector SCRFD sobre CPU. Un solo `detect()` por frame (2 fps basta)."""

    def __init__(self, model_path: str, input_size: tuple[int, int] = (640, 640), det_thresh: float = 0.5):
        opts = ort.SessionOptions()
        opts.log_severity_level = 3  # silencia el banner de onnxruntime
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.input_size = input_size
        self.det_thresh = det_thresh
        self._score_is_logit: bool | None = None  # autodetectado en el primer forward
        infos = [(o.name, o.shape) for o in self.session.get_outputs()]
        scores_n = [n for n, sh in infos if self._last_dim(sh) == 1]
        bboxes_n = [n for n, sh in infos if self._last_dim(sh) == 4]
        kps_n = [n for n, sh in infos if self._last_dim(sh) == 10]
        n_levels = min(len(scores_n), len(bboxes_n), len(kps_n))
        if n_levels == 0:
            raise ValueError(
                f"Export ONNX sin salidas (1,4,10) reconocibles: {[n for n, _ in infos]}"
            )
        groups = list(zip(scores_n, bboxes_n, kps_n, strict=True))
        self._groups: list[tuple[tuple[str, ...], int]] = [
            (g, s) for g, s in zip(groups, STRIDES[:n_levels], strict=True)
        ]

    # -- pre/post-proceso ----------------------------------------------------
    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        img = cv2.resize(frame, self.input_size, interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - DET_MEAN) / DET_STD
        return np.transpose(img, (2, 0, 1))[None]  # (1,3,H,W)

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-x))

    @staticmethod
    def _last_dim(shape: object) -> int:
        """Última dimensión declarada del output (-1 si es dinámica)."""
        try:
            last = list(shape)[-1]  # type: ignore[arg-type]
            return int(last)
        except (TypeError, ValueError, IndexError):
            return -1

    def _decode_stride(self, raw: dict[str, np.ndarray], names: tuple[str, ...], stride: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Devuelve (scores, boxes_xyxy, kps(N,10)) decodificados para un nivel FPN."""
        score_n, bbox_n, kps_n = names
        scores = raw[score_n].reshape(-1)
        bbox_d = raw[bbox_n].reshape(-1, 4) * stride
        kps_d = raw[kps_n].reshape(-1, 10) * stride

        in_h, in_w = self.input_size
        gh, gw = in_h // stride, in_w // stride
        centers = np.stack(np.mgrid[:gh, :gw][::-1], axis=-1).astype(np.float32)
        centers = (centers * stride).reshape(-1, 2)
        centers = np.stack([centers] * NUM_ANCHORS, axis=1).reshape(-1, 2)

        boxes = np.concatenate(
            [
                centers[:, 0:1] - bbox_d[:, 0:1],
                centers[:, 1:2] - bbox_d[:, 1:2],
                centers[:, 0:1] + bbox_d[:, 2:3],
                centers[:, 1:2] + bbox_d[:, 3:4],
            ],
            axis=1,
        )
        kps = np.empty_like(kps_d)
        kps[:, 0::2] = centers[:, 0:1] - kps_d[:, 0::2]
        kps[:, 1::2] = centers[:, 1:2] - kps_d[:, 1::2]
        return scores, boxes, kps

    # -- API -------------------------------------------------------------------
    def detect(self, frame: np.ndarray, det_thresh: float | None = None, max_faces: int = 0) -> list[Face]:
        """Detecta rostros. `max_faces>0` limita a los N de mayor score."""
        thresh = self.det_thresh if det_thresh is None else det_thresh
        h0, w0 = frame.shape[:2]
        inp = self._preprocess(frame)
        out = self.session.run(self.output_names, {self.input_name: inp})
        raw = dict(zip(self.output_names, out, strict=True))

        first = raw[self._groups[0][0][0]].reshape(-1)
        if self._score_is_logit is None:
            self._score_is_logit = bool((first.min() < -1e-6) or (first.max() > 1.0 + 1e-6))

        all_boxes, all_scores, all_kps = [], [], []
        for names, stride in self._groups:
            scores, boxes, kps = self._decode_stride(raw, names, stride)
            if self._score_is_logit:
                scores = self._sigmoid(scores)
            all_scores.append(scores)
            all_boxes.append(boxes)
            all_kps.append(kps)

        scores = np.concatenate(all_scores)
        boxes = np.concatenate(all_boxes)
        kps = np.concatenate(all_kps)

        sx, sy = w0 / self.input_size[0], h0 / self.input_size[1]
        boxes[:, [0, 2]] *= sx
        boxes[:, [1, 3]] *= sy
        kps[:, 0::2] *= sx
        kps[:, 1::2] *= sy

        keep_idx = np.where(scores >= thresh)[0]
        if len(keep_idx) == 0:
            return []
        boxes, scores, kps = boxes[keep_idx], scores[keep_idx], kps[keep_idx]
        order = nms(boxes, scores, iou_threshold=0.4)
        faces = [Face(box=boxes[i], score=float(scores[i]), kps=kps[i].reshape(5, 2)) for i in order]
        faces.sort(key=lambda f: f.score, reverse=True)
        return faces[:max_faces] if max_faces > 0 else faces

    def largest(self, frame: np.ndarray, det_thresh: float | None = None) -> Face | None:
        """El rostro de mayor confianza (el que está 'pidiendo paso')."""
        faces = self.detect(frame, det_thresh=det_thresh)
        return faces[0] if faces else None
