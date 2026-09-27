"""Fuentes de frames bajo una misma interfaz (RF-17, §4.3 del plan).

- ``VideoFileSource``: MP4/AVI en bucle - demos y tests SIN hardware.
- ``RtspSource``: cámara Hikvision real (sub-stream 102 recomendado).
- ``WebcamSource``: cámara del PC para pruebas rápidas.

El recolector corre en un HILO aparte con un buffer de 1 frame (siempre el
más reciente): los endpoints HTTP del proceso nunca se bloquean esperando un
frame, y el reconocedor siempre trabaja con video fresco. Graba el archivo si
la fuente falla al abrirse (ruta incorrecta, stream caído) en lugar de lanzar
una excepción tardía.
"""
import os
import threading
import time
from typing import Any

import cv2
import numpy as np

# FFMPEG: RTSP sobre TCP y timeout de stream de 5 s (µs) — sin esto, un host
# caído bloquea VideoCapture 30 s (medido). Siempre via to_thread además.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000"
)


class FrameSource:
    """Interfaz común: read() → (ok, frame BGR) al estilo de cv2.VideoCapture."""

    def read(self) -> tuple[bool, np.ndarray | None]:
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError


class _ThreadedSource(FrameSource):
    """Lee en background y deja solo el frame más reciente disponible."""

    def __init__(self, cap: cv2.VideoCapture, loop: bool, name: str) -> None:
        self._cap = cap
        self._loop = loop
        self._name = name
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._ok = False
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True, name=f"fareas-src-{name}")
        self._thread.start()

    def _reader(self) -> None:
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        delay = 1.0 / fps if fps and fps > 1 else 1.0 / 25.0  # ritmo de reproducción
        while not self._stopped.is_set():
            ok, frame = self._cap.read()
            if not ok:
                if self._loop:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # reinicia el MP4
                    continue
                with self._lock:
                    self._ok, self._frame = False, None
                break
            with self._lock:
                self._ok, self._frame = True, frame
            time.sleep(delay)

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._frame is None:
                return False, None
            return self._ok, self._frame

    def release(self) -> None:
        self._stopped.set()
        self._thread.join(timeout=2.0)
        self._cap.release()


class VideoFileSource(FrameSource):
    """Archivo de video en bucle - la 'puerta del aula' de las demos (§4.3)."""

    def __init__(self, path: str, loop: bool = True) -> None:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise FileNotFoundError(f"No se pudo abrir el video: {path}")
        self._src: FrameSource | cv2.VideoCapture
        self._src = _ThreadedSource(cap, loop=loop, name="video")

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self._src.read()

    def release(self) -> None:
        self._src.release()


class RtspSource(FrameSource):
    """Cámara IP por RTSP (RF-17). El buffer de 1 frame evita latencia acumulada."""

    def __init__(self, rtsp_url: str) -> None:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            raise FileNotFoundError(f"No se pudo abrir el stream RTSP (revisa URL/clave): {rtsp_url}")
        self._src: FrameSource | cv2.VideoCapture
        self._src = _ThreadedSource(cap, loop=False, name="rtsp")

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self._src.read()

    def release(self) -> None:
        self._src.release()


class WebcamSource(FrameSource):
    """Webcam local por índice (0 = cámara por defecto). Pruebas de escritorio."""

    def __init__(self, index: int = 0) -> None:
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            raise FileNotFoundError(f"No se pudo abrir la webcam #{index}")
        self._src: FrameSource | cv2.VideoCapture
        self._src = _ThreadedSource(cap, loop=False, name="webcam")

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self._src.read()

    def release(self) -> None:
        self._src.release()


def open_source(spec: str | int) -> FrameSource:
    """Fábrica: '0'→webcam, http/rtsp://→cámara IP, cualquier otra ruta→archivo."""
    if isinstance(spec, int):
        return WebcamSource(spec)
    s = str(spec).strip()
    if s == "0":
        return WebcamSource(0)
    if s.startswith(("rtsp://", "http://", "https://")):
        return RtspSource(s)
    return VideoFileSource(s)


def draw_face(frame: np.ndarray, box: Any, color: tuple[int, int, int], label: str = "") -> np.ndarray:
    """Dibuja una caja xyxy (y etiqueta opcional) sobre una COPIA del frame."""
    out = frame.copy()
    x1, y1, x2, y2 = (int(round(float(v))) for v in box[:4])
    cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
    if label:
        cv2.putText(out, label, (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return out
