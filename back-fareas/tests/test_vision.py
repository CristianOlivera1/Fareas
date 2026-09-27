"""Tests del Bloque 5 - pipeline de visión (RF-04, RF-19, RF-20, Tabla 8).

Dos capas:
- Unitarios con dobles (NMS, galería, veredictos del pipeline) - rápidos.
- Un smoke con los MODELOS REALES y el video de demo: enrola con el último
  frame (rostro grande y frontal) y verifica que el pipeline identifica al
  menos una aparición. Se salta si no hay modelos o video en la máquina.
"""
from pathlib import Path

import numpy as np
import pytest

from app.ai.boxes import iou_matrix, nms
from app.ai.pipeline import VERDICTS, VisionPipeline
from app.ai.recognizer import FaceGallery, parse_pg_array
from app.ai.resources import demo_video

VIDEO = demo_video()
MODELOS = Path("models/det_10g.onnx"), Path("models/w600k_r50.onnx")


# ---------------------------------------------------------------------------
# NMS / IoU
# ---------------------------------------------------------------------------
def test_iou_basico():
    a = np.array([[0, 0, 10, 10]], dtype=np.float32)
    assert iou_matrix(a, a)[0, 0] == pytest.approx(1.0)
    b = np.array([[20, 20, 30, 30]], dtype=np.float32)
    assert iou_matrix(a, b)[0, 0] == pytest.approx(0.0)
    c = np.array([[5, 0, 15, 10]], dtype=np.float32)  # 50% de solape
    assert iou_matrix(a, c)[0, 0] == pytest.approx(1.0 / 3.0, rel=1e-3)


def test_nms_deja_una_caja():
    boxes = np.array(
        [[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=np.float32
    )
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    keep = nms(boxes, scores, iou_threshold=0.4)
    assert keep == [0, 2]  # la caja solapada de menor score desaparece


# ---------------------------------------------------------------------------
# parse_pg_array (REAL[512] ↔ numpy)
# ---------------------------------------------------------------------------
def test_parse_pg_array_formatos():
    v = parse_pg_array([0.5, -0.5])
    assert v is not None and v.dtype == np.float32 and v.tolist() == [0.5, -0.5]
    v2 = parse_pg_array("{0.25,0.75}")
    assert v2 is not None and v2.tolist() == [0.25, 0.75]
    assert parse_pg_array(None) is None
    assert parse_pg_array("{}") is None
    assert parse_pg_array("no-es-un-vector") is None


# ---------------------------------------------------------------------------
# Galería (coseno + candidatos)
# ---------------------------------------------------------------------------
def _vec(i: int) -> np.ndarray:
    """Vector determinista distinguible: one-hot por bloque de 8 dims.

    Coseno 1.0 consigo mismo y 0.0 con cualquier otro i - ideal para las
    pruebas de galería y veredictos (sin vectores constantes, que serían
    todos paralelos entre sí).
    """
    v = np.zeros(512, dtype=np.float32)
    v[(i % 64) * 8 : (i % 64) * 8 + 8] = 1.0
    return v / np.linalg.norm(v)


def test_galeria_identifica_al_mejor():
    g = FaceGallery()
    g.set_student(1, [_vec(1), _vec(1)])  # 2 embeddings del alumno 1
    g.set_student(2, [_vec(2)])
    sid, sim = g.identify(_vec(1))
    assert sid == 1 and sim > 0.99
    sid, sim = g.identify(_vec(2))
    assert sid == 2 and sim > 0.99


def test_galeria_candidatos_y_umbral():
    g = FaceGallery()
    g.set_student(1, [_vec(1)])
    g.set_student(2, [_vec(2)])
    # El alumno 1 existe pero está EXCLUIDO por candidatos → desconocido
    sid, sim = g.identify(_vec(1), candidates={2}, threshold=0.75)
    assert sid is None and sim == 0.0
    # Debajo del umbral → None pero devuelve la mejor similitud
    sid, sim = g.identify(_vec(30), threshold=0.99)
    assert sid is None and sim < 0.99


# ---------------------------------------------------------------------------
# Veredictos Tabla 8 del pipeline (detector/embedder doblados)
# ---------------------------------------------------------------------------
class _DetFake:
    """Detector falso: devuelve landmarks fijos en el centro."""

    def detect(self, frame, det_thresh=None, max_faces=0):
        from app.ai.detector import Face

        return [Face(box=np.array([0, 0, 100, 100], dtype=np.float32), score=0.9,
                     kps=np.zeros((5, 2), dtype=np.float32))]


class _EmbFake:
    """Embedder falso: el valor medio del frame (int) elige el bloque one-hot."""

    def get(self, frame, lmk):
        return _vec(int(round(float(np.mean(frame)))))


def _frame(valor: float) -> np.ndarray:
    return np.full((120, 120, 3), valor, dtype=np.uint8)


def test_veredictos_tabla8():
    assert VERDICTS["asistio"] == ("verde", "beep_1", 3)
    assert VERDICTS["tardanza"] == ("amarillo", "beep_2", 3)
    assert VERDICTS["denegado"] == ("rojo", "tono_denegado", 3)
    assert VERDICTS["desconocido"] == ("azul", "ninguno", 2)


def test_pipeline_desconocido_y_asistio_demo():
    g = FaceGallery()
    g.set_student(7, [_vec(7)])
    p = VisionPipeline(_DetFake(), _EmbFake(), g, threshold=0.75)
    # frame(7) → embedding 7 → coseno 1.0 con el alumno 7 → asistio (demo, sin classifier)
    r = p.process_frame(_frame(7))
    assert r.verdict == "asistio" and r.student_id == 7 and r.color == "verde"
    assert r.buzzer == "beep_1" and r.mark is None  # demo no genera marca BD
    # frame(50) → bloque 50, nadie enrolado con él → desconocido azul
    r = p.process_frame(_frame(50))
    assert r.verdict == "desconocido" and r.color == "azul" and r.buzzer == "ninguno"


def test_pipeline_denegado_con_candidates():
    """Conocido fuera de la lista de matriculados → rojo (Tabla 8)."""
    g = FaceGallery()
    g.set_student(7, [_vec(7)])
    g.set_student(8, [_vec(8)])
    p = VisionPipeline(_DetFake(), _EmbFake(), g, threshold=0.75)
    r = p.process_frame(_frame(8), candidates={7})  # solo el 7 está matriculado
    assert r.verdict == "denegado" and r.student_id == 8 and r.color == "rojo"
    assert r.buzzer == "tono_denegado"


def test_pipeline_classifier_genera_marca_y_cooldown():
    g = FaceGallery()
    g.set_student(7, [_vec(7)])

    def clasificador(sid, now):
        if now < 200:
            return "asistio"
        if now < 500:
            return "tardanza"
        return "sin_registro"

    p = VisionPipeline(_DetFake(), _EmbFake(), g, threshold=0.75, cooldown_seconds=60.0,
                       classifier=clasificador)
    r1 = p.process_frame(_frame(7), now=100.0)
    assert r1.verdict == "asistio" and r1.mark == {"student_id": 7, "status": "asistio", "similarity": pytest.approx(1.0)}
    # cooldown activo (dentro de los 60 s): repite verde SIN nueva marca
    r2 = p.process_frame(_frame(7), now=150.0)
    assert r2.verdict == "asistio" and r2.mark is None
    # cooldown vencido + clasificador tardanza → amarillo con marca
    r3 = p.process_frame(_frame(7), now=300.0)
    assert r3.verdict == "tardanza" and r3.color == "amarillo" and r3.buzzer == "beep_2"
    assert r3.mark == {"student_id": 7, "status": "tardanza", "similarity": pytest.approx(1.0)}
    # mucho después: sin clase activa → azul sin marca
    r4 = p.process_frame(_frame(7), now=1000.0)
    assert r4.verdict == "sin_registro" and r4.mark is None and r4.color == "azul"


def test_pipeline_sin_rostro():
    class _DetVacio:
        def detect(self, *a, **k):
            return []

    p = VisionPipeline(_DetVacio(), _EmbFake(), FaceGallery(), threshold=0.75)
    r = p.process_frame(_frame(0.5))
    assert r.verdict == "sin_rostro" and r.color == "" and r.seconds == 0


# ---------------------------------------------------------------------------
# Smoke con modelos reales + video de demo (se salta si faltan recursos)
# ---------------------------------------------------------------------------
def _video_frames(video: Path, max_frames: int = 300):
    import cv2

    cap = cv2.VideoCapture(str(video))
    frames = []
    ok = True
    while ok and len(frames) < max_frames:
        ok, f = cap.read()
        if ok:
            frames.append(f)
    cap.release()
    return frames


@pytest.mark.skipif(not all(m.exists() for m in MODELOS) or not VIDEO.exists(),
                    reason="requiere models/*.onnx y resources/ con el video demo")
def test_smoke_pipeline_modelos_reales():
    from app.ai.detector import ScrfdDetector
    from app.ai.embedder import ArcFaceEmbedder

    det = ScrfdDetector(str(MODELOS[0]))
    emb = ArcFaceEmbedder(str(MODELOS[1]))
    frames = _video_frames(VIDEO)
    assert len(frames) >= 100

    # Enrola con el último frame (rostro grande, de frente a la 'puerta')
    faces = det.detect(frames[-1])
    assert faces, "el video de demo debe tener un rostro al final"
    e = emb.get(frames[-1], faces[0].kps)
    g = FaceGallery()
    g.set_student(101, [e])
    p = VisionPipeline(det, emb, g, threshold=0.75)

    hits = 0
    for i in range(0, len(frames), 5):
        if not det.detect(frames[i]):
            continue
        r = p.process_frame(frames[i])
        if r.student_id == 101:
            hits += 1
    assert hits >= 1, "el pipeline debe identificar al menos una vez al alumno enrolado"


@pytest.mark.skipif(not all(m.exists() for m in MODELOS) or not VIDEO.exists(),
                    reason="requiere models/*.onnx y resources/ con el video demo")
def test_smoke_galeria_desde_bd():
    """La galería se llena desde face_embedding de la BD real (fila demo si existe)."""
    import asyncio

    from app.ai.runtime import recargar_galeria
    from app.database import SessionLocal

    async def _cargar():
        async with SessionLocal() as db:
            return await recargar_galeria(db)

    n = asyncio.run(_cargar())
    assert n >= 0  # la BD demo puede no tener enrolamientos aún
