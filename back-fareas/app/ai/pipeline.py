import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.ai.detector import Face, ScrfdDetector
from app.ai.embedder import ArcFaceEmbedder
from app.ai.recognizer import FaceGallery

COLORS: dict[str, tuple[int, int, int]] = {
    "verde": (0, 200, 0),
    "amarillo": (0, 200, 200),
    "rojo": (0, 0, 220),
    "azul": (255, 100, 0),
}

MESSAGES: dict[str, str] = {
    "asistio": "Registro correcto",
    "tardanza": "Registro con tardanza",
    "denegado": "No estas matriculado en esta clase",
    "desconocido": "Rostro no reconocido",
    "sin_registro": "Sin clase activa para este aula",
    "verificando": "Verificando rostro",
}

VERDICTS: dict[str, tuple[str, str, int]] = {
    "asistio": ("verde", "beep_1", 3),
    "tardanza": ("amarillo", "beep_2", 3),
    "denegado": ("rojo", "tono_denegado", 3),
    "desconocido": ("azul", "ninguno", 2),
    "sin_registro": ("azul", "ninguno", 2),
}


@dataclass
class FrameResult:
    faces: list[Face] = field(default_factory=list)
    verdict: str = "sin_rostro"
    color: str = ""
    buzzer: str = "ninguno"
    seconds: int = 0
    student_id: int | None = None
    similarity: float = 0.0
    message: str = ""
    box: Any = None
    mark: dict | None = None

    def as_ws_command(self) -> dict:
        return {"type": "verdict", "status": self.verdict, "message": self.message,
                "color": self.color, "buzzer": self.buzzer, "seconds": self.seconds}

class VisionPipeline:
    def __init__(
        self,
        detector: ScrfdDetector,
        embedder: ArcFaceEmbedder,
        gallery: FaceGallery,
        threshold: float = 0.75,
        cooldown_seconds: float = 30.0,
        classifier: Callable[[int, float], str] | None = None,
        margin: float = 0.0,
        confirm_frames: int = 1,
        min_face_px: int = 0,
    ) -> None:
        self.detector = detector
        self.embedder = embedder
        self.gallery = gallery
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.classifier = classifier
        self.margin = margin
        self.confirm_frames = max(1, confirm_frames)
        self.min_face_px = min_face_px
        self._last_mark: dict[int, float] = {}
        self._streaks: dict[object, tuple[int, int]] = {}
        self._clock: Callable[[], float] = time.monotonic

    @staticmethod
    def _area(face: Face) -> float:
        return float(max(0.0, face.box[2] - face.box[0]) * max(0.0, face.box[3] - face.box[1]))

    def _big_enough(self, face: Face) -> bool:
        width = float(face.box[2] - face.box[0])
        height = float(face.box[3] - face.box[1])
        return min(width, height) >= self.min_face_px

    def _confirmed(self, track_key: object, sid: int) -> bool:
        last_sid, count = self._streaks.get(track_key, (-1, 0))
        count = count + 1 if last_sid == sid else 1
        self._streaks[track_key] = (sid, count)
        return count >= self.confirm_frames

    def process_frame(
        self,
        frame: np.ndarray,
        candidates: set[int] | None = None,
        now: float | None = None,
        track_key: object = None,
    ) -> FrameResult:
        faces = [f for f in self.detector.detect(frame, max_faces=5) if self._big_enough(f)]
        if not faces:
            self._streaks.pop(track_key, None)
            return FrameResult(verdict="sin_rostro", color="", buzzer="ninguno", seconds=0, message="")

        faces.sort(key=lambda f: self._area(f), reverse=True)
        face = faces[0]
        embedding = self.embedder.get(frame, face.kps)
        sid, sim = self.gallery.identify(
            embedding, candidates=candidates, threshold=self.threshold, margin=self.margin
        )

        if sid is not None and not self._confirmed(track_key, sid):
            return FrameResult(
                faces=faces, verdict="verificando", color="azul", buzzer="ninguno",
                seconds=1, student_id=sid, similarity=sim, message=MESSAGES["verificando"], box=face.box,
            )
        if sid is None:
            self._streaks.pop(track_key, None)
            if candidates is not None:
                other, other_sim = self.gallery.identify(
                    embedding, candidates=None, threshold=self.threshold, margin=self.margin
                )
                if other is not None:
                    return FrameResult(
                        faces=faces, verdict="denegado", color="rojo", buzzer="tono_denegado",
                        seconds=3, student_id=other, similarity=other_sim,
                        message=MESSAGES["denegado"], box=face.box,
                    )
            return FrameResult(
                faces=faces, verdict="desconocido", color="azul", buzzer="ninguno",
                seconds=2, similarity=sim, message=MESSAGES["desconocido"], box=face.box,
            )

        clock_now = self._clock() if now is None else now

        if self.classifier is not None and (clock_now - self._last_mark.get(sid, -1e9)) < self.cooldown_seconds:
            return FrameResult(
                faces=faces, verdict="asistio", color="verde", buzzer="beep_1",
                seconds=2, student_id=sid, similarity=sim,
                message=MESSAGES["asistio"], box=face.box,
            )

        mark = None
        if self.classifier is not None:
            status = self.classifier(sid, clock_now)
            if status == "sin_registro":
                return FrameResult(
                    faces=faces, verdict="sin_registro", color="azul", buzzer="ninguno",
                    seconds=2, student_id=sid, similarity=sim,
                    message=MESSAGES["sin_registro"], box=face.box,
                )
            mark = {"student_id": sid, "status": status, "similarity": sim}
            self._last_mark[sid] = clock_now

        verdict = mark["status"] if mark else "asistio"
        color, buzzer, seconds = VERDICTS[verdict]
        return FrameResult(
            faces=faces, verdict=verdict, color=color, buzzer=buzzer, seconds=seconds,
            student_id=sid, similarity=sim, message=MESSAGES[verdict], box=face.box, mark=mark,
        )
