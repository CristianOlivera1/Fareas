import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator

import cv2

import app.ai.frame_source  # noqa: F401

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


def _encode(frame) -> bytes | None:
    height, width = frame.shape[:2]
    if width > MAX_WIDTH:
        frame = cv2.resize(
            frame, (MAX_WIDTH, int(height * MAX_WIDTH / width)), interpolation=cv2.INTER_AREA
        )
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
        self.idle_since: float | None = None
        self.sequence = 0
        self.jpeg: bytes | None = None
        self.ended = False
        self._capture = capture
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"cam-{room_id}", daemon=True)
        self._thread.start()

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
            now = time.monotonic()
            if now - last_encoded < interval:
                continue
            last_encoded = now
            jpeg = _encode(frame)
            if jpeg:
                self.jpeg = jpeg
                self.sequence += 1
        self.ended = True
        self._capture.release()

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


async def _acquire(room_id: int, rtsp_url: str) -> _RoomReader:
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
        if reader.viewers >= MAX_VIEWERS_PER_ROOM:
            raise StreamBusy()
        reader.viewers += 1
        reader.idle_since = None
        return reader


async def _release(reader: _RoomReader) -> None:
    async with _lock:
        reader.viewers = max(0, reader.viewers - 1)
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


def viewers(room_id: int) -> int:
    reader = _readers.get(room_id)
    return reader.viewers if reader else 0


def shutdown() -> None:
    for reader in list(_readers.values()):
        reader.stop()
    _readers.clear()
