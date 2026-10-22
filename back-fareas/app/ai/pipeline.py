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
    ) -> None:
        self.detector = detector
        self.embedder = embedder
        self.gallery = gallery
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.classifier = classifier
        self._last_mark: dict[int, float] = {}
        self._clock: Callable[[], float] = time.monotonic

    def process_frame(
        self,
        frame: np.ndarray,
        candidates: set[int] | None = None,
        now: float | None = None,
    ) -> FrameResult:
        faces = self.detector.detect(frame, max_faces=5)
        if not faces:
            return FrameResult(verdict="sin_rostro", color="", buzzer="ninguno", seconds=0, message="")

        face = faces[0]
        embedding = self.embedder.get(frame, face.kps)
        sid, sim = self.gallery.identify(embedding, candidates=candidates, threshold=self.threshold)

        if sid is None:
            if candidates is not None:
                other, other_sim = self.gallery.identify(embedding, candidates=None, threshold=self.threshold)
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
