import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator

import cv2
import numpy as np

import app.ai.frame_source  # noqa: F401
from app.ai.pipeline import MESSAGES

logger = logging.getLogger("fareas.camera_stream")

BOUNDARY = "frame"
MAX_WIDTH = 960
JPEG_QUALITY = 75
TARGET_FPS = 15
MAX_VIEWERS_PER_ROOM = 6
RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_S = 1.0
IDLE_GRACE_S = 5.0
POLL_S = 0.02
DETECT_WIDTH = 640
DETECT_THRESHOLD = 0.5
DETECT_IDLE_S = 0.02
DETECT_MIN_INTERVAL_S = 0.2
BOX_MAX_AGE_S = 0.6

DETECTED_COLOR = (80, 200, 60)
VERDICT_COLORS: dict[str, tuple[int, int, int]] = {
    "asistio": (80, 200, 60),
    "tardanza": (30, 190, 240),
    "denegado": (60, 60, 230),
    "desconocido": (230, 150, 40),
    "sin_registro": (230, 150, 40),
    "verificando": (230, 150, 40),
}


class StreamBusy(Exception):
    pass


class StreamUnavailable(Exception):
    pass


def _open(rtsp_url: str) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    if not capture.isOpened():
        capture.release()
        raise StreamUnavailable("No se pudo abrir el stream RTSP de la cámara")
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def _draw_face(frame, box, color: tuple[int, int, int], label: str | None) -> None:
    x1, y1, x2, y2 = (int(round(float(v))) for v in box)
    height, width = frame.shape[:2]
    thickness = max(2, round(width / 320))
    arm = max(10, int(min(x2 - x1, y2 - y1) * 0.22))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)
    for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(frame, (cx, cy), (cx + dx * arm, cy), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * arm), color, thickness, cv2.LINE_AA)
    if not label:
        return
    scale = max(0.45, width / 1600)
    (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    top = y1 - text_h - baseline - 8
    if top < 0:
        top = y2 + 4
    cv2.rectangle(frame, (x1, top), (x1 + text_w + 12, top + text_h + baseline + 8), color, -1)
    cv2.putText(
        frame, label, (x1 + 6, top + text_h + 3), cv2.FONT_HERSHEY_SIMPLEX, scale,
        (255, 255, 255), 1, cv2.LINE_AA,
    )


def _overlay(frame, boxes, ratio: float, verdict: dict | None) -> None:
    color = VERDICT_COLORS.get(verdict["verdict"], DETECTED_COLOR) if verdict else DETECTED_COLOR
    label = MESSAGES.get(verdict["verdict"]) if verdict else None
    for index, box in enumerate(boxes):
        _draw_face(frame, np.asarray(box, dtype=np.float32) * ratio, color if index == 0 else DETECTED_COLOR,
                   label if index == 0 else None)


def _encode(frame, boxes=(), verdict: dict | None = None) -> bytes | None:
    height, width = frame.shape[:2]
    ratio = 1.0
    if width > MAX_WIDTH:
        ratio = MAX_WIDTH / width
        frame = cv2.resize(frame, (MAX_WIDTH, int(height * ratio)), interpolation=cv2.INTER_AREA)
    elif boxes:
        frame = frame.copy()
    if boxes:
        _overlay(frame, boxes, ratio, verdict)
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buffer.tobytes() if ok else None


def _part(jpeg: bytes) -> bytes:
    header = f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
    return header.encode() + jpeg + b"\r\n"


class _RoomReader:
    def __init__(self, room_id: int, rtsp_url: str, capture: cv2.VideoCapture) -> None:
        self.room_id = room_id
        self.rtsp_url = rtsp_url
        self.viewers = 0
        self.video_viewers = 0
        self.frame_size = (0, 0)
        self.boxes_sequence = 0
        self.idle_since: float | None = None
        self.sequence = 0
        self.jpeg: bytes | None = None
        self.ended = False
        self._raw = None
        self._raw_sequence = 0
        self._boxes: list = []
        self._boxes_at = 0.0
        self._capture = capture
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"cam-{room_id}", daemon=True)
        self._detector_thread = threading.Thread(target=self._detect, name=f"det-{room_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._detector_thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        interval = 1.0 / TARGET_FPS
        last_encoded = 0.0
        failures = 0
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if not ok or frame is None:
                if not self._reconnect(failures):
                    break
                failures += 1
                continue
            failures = 0
            self._raw = frame
            self._raw_sequence += 1
            self.frame_size = (frame.shape[1], frame.shape[0])
            now = time.monotonic()
            if self.video_viewers == 0 or now - last_encoded < interval:
                continue
            last_encoded = now
            jpeg = _encode(frame, self.current_boxes(now), self._verdict())
            if jpeg:
                self.jpeg = jpeg
                self.sequence += 1
        self.ended = True
        self._capture.release()

    def current_boxes(self, now: float) -> list:
        return self._boxes if now - self._boxes_at <= BOX_MAX_AGE_S else []

    def _verdict(self) -> dict | None:
        from app.services.camera_loop import veredicto_reciente

        return veredicto_reciente(self.room_id)

    def _detect(self) -> None:
        try:
            from app.ai.runtime import detector

            model = detector()
        except Exception:
            logger.warning("Sin detector facial; el video no mostrará recuadros", exc_info=True)
            return
        seen = 0
        while not self._stop.is_set():
            frame, sequence = self._raw, self._raw_sequence
            if frame is None or sequence == seen:
                self._stop.wait(DETECT_IDLE_S)
                continue
            seen = sequence
            started = time.monotonic()
            width = frame.shape[1]
            ratio = DETECT_WIDTH / width if width > DETECT_WIDTH else 1.0
            small = cv2.resize(frame, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA) if ratio < 1.0 else frame
            try:
                faces = model.detect(small, det_thresh=DETECT_THRESHOLD, max_faces=5)
            except Exception:
                logger.exception("Falló la detección facial del stream")
                self._stop.wait(1.0)
                continue
            faces.sort(key=lambda f: (f.box[2] - f.box[0]) * (f.box[3] - f.box[1]), reverse=True)
            self._boxes = [face.box / ratio for face in faces]
            self._boxes_at = time.monotonic()
            self.boxes_sequence += 1
            self._stop.wait(max(0.0, DETECT_MIN_INTERVAL_S - (time.monotonic() - started)))

    def _reconnect(self, failures: int) -> bool:
        if failures >= RECONNECT_ATTEMPTS:
            logger.warning("Stream de la sala %s sin frames; se cierra", self.room_id)
            return False
        self._capture.release()
        self._stop.wait(RECONNECT_DELAY_S)
        if self._stop.is_set():
            return False
        try:
            self._capture = _open(self.rtsp_url)
        except StreamUnavailable:
            pass
        return True


_readers: dict[int, _RoomReader] = {}
_lock = asyncio.Lock()


async def _acquire(room_id: int, rtsp_url: str, video: bool = True) -> _RoomReader:
    async with _lock:
        reader = _readers.get(room_id)
        if reader is not None and (reader.ended or reader.rtsp_url != rtsp_url):
            reader.stop()
            _readers.pop(room_id, None)
            reader = None
        if reader is None:
            capture = await asyncio.to_thread(_open, rtsp_url)
            reader = _RoomReader(room_id, rtsp_url, capture)
            _readers[room_id] = reader
            started = False
        else:
            started = True
        if reader.viewers >= MAX_VIEWERS_PER_ROOM:
            raise StreamBusy()
        reader.viewers += 1
        reader.video_viewers += 1 if video else 0
        if not started:
            reader.start()
        reader.idle_since = None
        return reader


async def _release(reader: _RoomReader, video: bool = True) -> None:
    async with _lock:
        reader.viewers = max(0, reader.viewers - 1)
        reader.video_viewers = max(0, reader.video_viewers - (1 if video else 0))
        if reader.viewers == 0:
            reader.idle_since = time.monotonic()
    await asyncio.sleep(IDLE_GRACE_S)
    async with _lock:
        if reader.viewers == 0 and _readers.get(reader.room_id) is reader:
            reader.stop()
            _readers.pop(reader.room_id, None)


async def mjpeg_frames(room_id: int, rtsp_url: str) -> AsyncIterator[bytes]:
    reader = await _acquire(room_id, rtsp_url)
    seen = 0
    waited = 0.0
    try:
        while True:
            if reader.sequence != seen and reader.jpeg is not None:
                seen = reader.sequence
                waited = 0.0
                yield _part(reader.jpeg)
                continue
            if reader.ended and reader.sequence == seen:
                return
            await asyncio.sleep(POLL_S)
            waited += POLL_S
            if waited > 15:
                return
    finally:
        asyncio.get_running_loop().create_task(_release(reader))


async def face_events(room_id: int, rtsp_url: str) -> AsyncIterator[dict]:
    from app.services.camera_loop import veredicto_reciente

    reader = await _acquire(room_id, rtsp_url, video=False)
    seen = 0
    waited = 0.0
    try:
        while not reader.ended:
            if reader.boxes_sequence != seen and reader.frame_size[0] > 0:
                seen = reader.boxes_sequence
                waited = 0.0
                width, height = reader.frame_size
                verdict = veredicto_reciente(room_id)
                yield {
                    "boxes": [
                        [round(float(b[0]) / width, 4), round(float(b[1]) / height, 4),
                         round(float(b[2]) / width, 4), round(float(b[3]) / height, 4)]
                        for b in reader.current_boxes(time.monotonic())
                    ],
                    "verdict": verdict["verdict"] if verdict else None,
                    "label": MESSAGES.get(verdict["verdict"]) if verdict else None,
                }
                continue
            await asyncio.sleep(POLL_S)
            waited += POLL_S
            if waited > 15:
                return
    finally:
        asyncio.get_running_loop().create_task(_release(reader, video=False))


def viewers(room_id: int) -> int:
    reader = _readers.get(room_id)
    return reader.viewers if reader else 0


def shutdown() -> None:
    for reader in list(_readers.values()):
        reader.stop()
    _readers.clear()
