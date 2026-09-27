"""pipeline.process_frame(): el corazón del Bloque 5 (lo consume el Bloque 6).

Frame → detectar (SCRFD) → embeddear (ArcFace) → identificar (coseno) →
veredicto de puerta según la Tabla 8 (lo que entienden LED + buzzer del
ESP32, RF-27…RF-29):

| Situación                                   | LED      | Buzzer        |
|---------------------------------------------|----------|---------------|
| Asistió                                     | verde    | beep_1        |
| Tardanza                                    | amarillo | beep_2        |
| Conocido pero no matriculado en esta clase  | rojo     | tono_denegado |
| Desconocido / sin clase activa              | azul     | ninguno       |
| Sin rostro en el frame                      | -        | ninguno       |

El clasificador (asistio/tardanza/sin_registro) lo inyecta el Bloque 6
resolviendo la sesión activa del aula y la tolerancia RF-23; en modo demo
(classifier=None) todo rostro conocido responde verde sin tocar la BD.
"""
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.ai.detector import Face, ScrfdDetector
from app.ai.embedder import ArcFaceEmbedder
from app.ai.recognizer import FaceGallery

# Paleta BGR para overlays y referencia de colores que viajan al nodo.
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

# Tabla 8: verdicto -> (color, buzzer, segundos de estímulo)
VERDICTS: dict[str, tuple[str, str, int]] = {
    "asistio": ("verde", "beep_1", 3),
    "tardanza": ("amarillo", "beep_2", 3),
    "denegado": ("rojo", "tono_denegado", 3),
    "desconocido": ("azul", "ninguno", 2),
    "sin_registro": ("azul", "ninguno", 2),
}


@dataclass
class FrameResult:
    """Resultado de procesar UN frame: para la puerta y para el dashboard."""

    faces: list[Face] = field(default_factory=list)
    verdict: str = "sin_rostro"
    color: str = ""
    buzzer: str = "ninguno"
    seconds: int = 0
    student_id: int | None = None
    similarity: float = 0.0
    message: str = ""
    box: Any = None
    mark: dict | None = None  # {'student_id','status','similarity'} - el Bloque 6 lo persiste

    def as_ws_command(self) -> dict:
        """Payload listo para el comando 'verdict' del protocolo ESP32 (§4.2)."""
        return {"type": "verdict", "status": self.verdict, "message": self.message,
                "color": self.color, "buzzer": self.buzzer, "seconds": self.seconds}


class VisionPipeline:
    """Ensambla detector + embedder + galería y produce veredictos Tabla 8."""

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
        self.classifier = classifier  # Bloque 6: (student_id, now) -> asistio|tardanza|sin_registro
        self._last_mark: dict[int, float] = {}  # student_id -> clock() de su última marca
        self._clock: Callable[[], float] = time.monotonic  # reemplazable en tests

    def process_frame(
        self,
        frame: np.ndarray,
        candidates: set[int] | None = None,
        now: float | None = None,
    ) -> FrameResult:
        """Procesa un frame y devuelve el veredicto de la puerta.

        ``candidates`` = alumnos matriculados en la clase activa del aula;
        ``None`` = toda la galería (modo demo, sin BD).
        """
        faces = self.detector.detect(frame, max_faces=5)
        if not faces:
            return FrameResult(verdict="sin_rostro", color="", buzzer="ninguno", seconds=0, message="")

        face = faces[0]  # el de mayor score: el que está pidiendo paso
        embedding = self.embedder.get(frame, face.kps)
        sid, sim = self.gallery.identify(embedding, candidates=candidates, threshold=self.threshold)

        if sid is None:
            # ¿Es alguien conocido pero de otra clase? → denegado (rojo, Tabla 8)
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

        # Cooldown: al alumno ya se le marcó hace poco → solo repite el verde.
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
