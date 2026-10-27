from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from app.ai.boxes import nms

DET_MEAN = 127.5
DET_STD = 128.0

STRIDES = (8, 16, 32)
SIZE_MULTIPLE = 32
NUM_ANCHORS = 2


@dataclass(frozen=True)
class Face:
    box: np.ndarray
    score: float
    kps: np.ndarray

class ScrfdDetector:
    def __init__(self, model_path: str, input_size: tuple[int, int] = (640, 640), det_thresh: float = 0.5):
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.input_size = input_size
        self.adaptive_size = True
        self.det_thresh = det_thresh
        self._score_is_logit: bool | None = None
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

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        limit_w, limit_h = self.input_size
        h0, w0 = frame.shape[:2]
        scale = min(limit_w / w0, limit_h / h0)
        new_w, new_h = max(1, int(round(w0 * scale))), max(1, int(round(h0 * scale)))
        if self.adaptive_size:
            in_w = -(-new_w // SIZE_MULTIPLE) * SIZE_MULTIPLE
            in_h = -(-new_h // SIZE_MULTIPLE) * SIZE_MULTIPLE
        else:
            in_w, in_h = limit_w, limit_h
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.zeros((in_h, in_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = resized
        img = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - DET_MEAN) / DET_STD
        return np.transpose(img, (2, 0, 1))[None], scale

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-x))

    @staticmethod
    def _last_dim(shape: object) -> int:
        try:
            last = list(shape)[-1]
            return int(last)
        except (TypeError, ValueError, IndexError):
            return -1

    def _decode_stride(
        self, raw: dict[str, np.ndarray], names: tuple[str, ...], stride: int, in_h: int, in_w: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        score_n, bbox_n, kps_n = names
        scores = raw[score_n].reshape(-1)
        bbox_d = raw[bbox_n].reshape(-1, 4) * stride
        kps_d = raw[kps_n].reshape(-1, 10) * stride

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
        kps[:, 0::2] = centers[:, 0:1] + kps_d[:, 0::2]
        kps[:, 1::2] = centers[:, 1:2] + kps_d[:, 1::2]
        return scores, boxes, kps

    def detect(self, frame: np.ndarray, det_thresh: float | None = None, max_faces: int = 0) -> list[Face]:
        thresh = self.det_thresh if det_thresh is None else det_thresh
        inp, scale = self._preprocess(frame)
        in_h, in_w = inp.shape[2], inp.shape[3]
        out = self.session.run(self.output_names, {self.input_name: inp})
        raw = dict(zip(self.output_names, out, strict=True))

        first = raw[self._groups[0][0][0]].reshape(-1)
        if self._score_is_logit is None:
            self._score_is_logit = bool((first.min() < -1e-6) or (first.max() > 1.0 + 1e-6))

        all_boxes, all_scores, all_kps = [], [], []
        for names, stride in self._groups:
            scores, boxes, kps = self._decode_stride(raw, names, stride, in_h, in_w)
            if self._score_is_logit:
                scores = self._sigmoid(scores)
            all_scores.append(scores)
            all_boxes.append(boxes)
            all_kps.append(kps)

        scores = np.concatenate(all_scores)
        boxes = np.concatenate(all_boxes)
        kps = np.concatenate(all_kps)

        boxes /= scale
        kps /= scale

        keep_idx = np.where(scores >= thresh)[0]
        if len(keep_idx) == 0:
            return []
        boxes, scores, kps = boxes[keep_idx], scores[keep_idx], kps[keep_idx]
        order = nms(boxes, scores, iou_threshold=0.4)
        faces = [Face(box=boxes[i], score=float(scores[i]), kps=kps[i].reshape(5, 2)) for i in order]
        faces.sort(key=lambda f: f.score, reverse=True)
        return faces[:max_faces] if max_faces > 0 else faces

    def largest(self, frame: np.ndarray, det_thresh: float | None = None) -> Face | None:
        faces = self.detect(frame, det_thresh=det_thresh)
        return faces[0] if faces else None
