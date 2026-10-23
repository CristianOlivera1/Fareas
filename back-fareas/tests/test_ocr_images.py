from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from sqlmodel import delete, select

from app.services.ocr_extract import leer_documento
from app.services.ocr_schedule import extraer_horarios_documento
from app.tables import AppUser, Course, CourseGroup, Enrollment, Room, ScheduleBlock, UserRole
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"
CODIGOS = ("TSTIMG901", "TSTIMG902", "TSTIMG903")
AULA_EXTRA = "TST-IMG-2"
DOCENTE_EXTRA = "temp.docente.ocr2@unamba.edu.pe"


def _fuente(tamano: int):
    for ruta in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def _imagen_horario() -> bytes:
    imagen = Image.new("RGB", (1600, 900), "white")
    dibujo = ImageDraw.Draw(imagen)
    fuente = _fuente(36)
    y = 50
    for linea in [
        "HORARIO DE CLASES",
        f"{CODIGOS[0]} ALGEBRA LINEAL            GRUPO A",
        "LUNES 07:00 - 09:00 AULA 305",
        "MIERCOLES 09:00 - 11:00 AULA 305",
        f"{CODIGOS[1]} PROGRAMACION I            GRUPO B",
        "MARTES 11:00 - 13:00 AULA 306",
    ]:
        dibujo.text((50, y), linea, fill="black", font=fuente)
        y += 80
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_escaneado_con_horario() -> bytes:
    buffer = BytesIO()
    pdf = rl_canvas.Canvas(buffer, pagesize=(1600, 900))
    pdf.drawImage(ImageReader(BytesIO(_imagen_horario())), 0, 0, width=1600, height=900)
    pdf.save()
    return buffer.getvalue()


async def _limpiar_codigos(db) -> None:
    for codigo in CODIGOS:
        curso = (await db.exec(select(Course).where(Course.code == codigo))).first()
        if curso is None:
            continue
        grupos = (
            await db.exec(select(CourseGroup).where(CourseGroup.course_id == curso.id))
        ).all()
        for grupo in grupos:
            await db.exec(delete(ScheduleBlock).where(ScheduleBlock.group_id == grupo.id))
            await db.exec(delete(Enrollment).where(Enrollment.group_id == grupo.id))
            await db.delete(grupo)
            await db.flush()
        await db.delete(curso)
    aula = (await db.exec(select(Room).where(Room.code == AULA_EXTRA))).first()
    if aula is not None:
        await db.delete(aula)
    docente = (
        await db.exec(select(AppUser).where(AppUser.email == DOCENTE_EXTRA))
    ).first()
    if docente is not None:
        await db.delete(docente)
    await db.commit()


@pytest.fixture
async def escenario(db_session):
    await _limpiar_codigos(db_session)
    await limpiar(db_session)
    datos = await crear(db_session)
    yield datos
    await _limpiar_codigos(db_session)
    await limpiar(db_session)


def _subir(client, headers, contenido: bytes, nombre: str, tipo: str):
    return client.post(
        f"{API}/courses/import-pdf",
        headers=headers,
        files={"file": (nombre, BytesIO(contenido), tipo)},
    )


def test_ocr_imagen_extrae_horario():
    documento = leer_documento(_imagen_horario(), "horario.png")
    assert documento.tipo == "imagen"
    assert documento.paginas == 1
    bloques = extraer_horarios_documento(documento)
    assert len(bloques) == 3
    assert all(bloque.confiable for bloque in bloques)
    assert [(b.course_code, b.weekday) for b in bloques] == [
        (CODIGOS[0], 1), (CODIGOS[0], 3), (CODIGOS[1], 2),
    ]


def test_pdf_escaneado_usa_ocr():
    documento = leer_documento(_pdf_escaneado_con_horario(), "horario.pdf")
    assert documento.tipo == "pdf_ocr"
    bloques = extraer_horarios_documento(documento)
    assert len(bloques) == 3
    assert all(bloque.confiable for bloque in bloques)


async def test_preview_imagen_por_api(client, admin_headers):
    r = await _subir(client, admin_headers, _imagen_horario(), "horario.png", "image/png")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tipo"] == "imagen"
    assert data["total"] == 3
    assert data["confiables"] == 3
    assert data["ambiguousos"] == 0
    assert {b["course_code"] for b in data["bloques"]} == {CODIGOS[0], CODIGOS[1]}


async def test_preview_imagen_rechaza_docente(client, docente_headers):
    r = await _subir(client, docente_headers, _imagen_horario(), "horario.png", "image/png")
    assert r.status_code == 403


async def test_confirmar_periodo_y_aula_por_fila(client, admin_headers, db_session, escenario):
    esc = escenario
    extra = Room(code=AULA_EXTRA, name="Aula OCR extra")
    db_session.add(extra)
    await db_session.commit()
    await db_session.refresh(extra)

    r = await _subir(client, admin_headers, _imagen_horario(), "horario.png", "image/png")
    bloques = [
        {
            "course_code": b["course_code"], "course_name": b["course_name"],
            "group_code": b["group_code"], "weekday": b["weekday"],
            "start_time": b["start_time"], "end_time": b["end_time"],
            "room_id": extra.id if b["course_code"] == CODIGOS[1] else esc["aula_id"],
        }
        for b in r.json()["bloques"]
    ]
    payload = {
        "teacher_id": esc["docente_id"], "room_id": esc["aula_id"],
        "cycle": 9, "semester_label": "2027-I", "bloques": bloques,
    }
    r = await client.post(f"{API}/courses/import-pdf/confirm", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["bloques_creados"] == 3 and data["omitidos"] == 0

    curso = (
        await db_session.exec(select(Course).where(Course.code == CODIGOS[0]))
    ).first()
    grupo = (
        await db_session.exec(
            select(CourseGroup).where(
                CourseGroup.course_id == curso.id,
                CourseGroup.group_code == "A",
                CourseGroup.semester_label == "2027-I",
            )
        )
    ).first()
    assert grupo is not None
    assert len(
        (await db_session.exec(select(ScheduleBlock).where(ScheduleBlock.group_id == grupo.id))).all()
    ) == 2

    r = await client.post(f"{API}/courses/import-pdf/confirm", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    repetido = r.json()
    assert repetido["bloques_creados"] == 0
    assert repetido["omitidos"] == 3


async def test_grupo_con_dos_docentes_revierte(client, admin_headers, db_session, escenario):
    esc = escenario
    otro = AppUser(
        role=UserRole.DOCENTE, email=DOCENTE_EXTRA, full_name="Docente OCR Dos",
        password_hash="x" * 20, must_change_password=False, dni="74449999",
    )
    db_session.add(otro)
    await db_session.commit()
    await db_session.refresh(otro)

    payload = {
        "teacher_id": esc["docente_id"], "room_id": esc["aula_id"], "cycle": 9,
        "semester_label": "2027-I",
        "bloques": [
            {"course_code": CODIGOS[2], "course_name": "Choque docente", "group_code": "A",
             "weekday": 1, "start_time": "07:00", "end_time": "09:00"},
            {"course_code": CODIGOS[2], "course_name": "Choque docente", "group_code": "A",
             "weekday": 2, "start_time": "07:00", "end_time": "09:00",
             "teacher_id": otro.id},
        ],
    }
    r = await client.post(f"{API}/courses/import-pdf/confirm", headers=admin_headers, json=payload)
    assert r.status_code == 422
    assert "un solo docente" in r.json()["detail"]
    curso = (
        await db_session.exec(select(Course).where(Course.code == CODIGOS[2]))
    ).first()
    assert curso is None


async def test_archivo_demasiado_grande(client, admin_headers):
    r = await _subir(client, admin_headers, b"x" * (10 * 1024 * 1024 + 1), "grande.png", "image/png")
    assert r.status_code == 413
