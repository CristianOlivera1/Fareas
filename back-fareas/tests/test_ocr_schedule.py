"""OCR de horarios - RF-07 (Bloque 9): preview de PDF y confirmación.

El PDF de prueba se genera en memoria con reportlab (constancia simulada).
El escenario B6 aporta aula+docente reales para la confirmación.
"""
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas as rl_canvas
from sqlmodel import delete, select

from app.services.ocr_schedule import extraer_horarios
from app.tables import Course, CourseGroup, ScheduleBlock
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"
TST_CURSO_OCR = "TSTOCR901"
TST_CURSO_OCR2 = "TSTOCR902"


def _pdf_matricula() -> bytes:
    """Constancia de matrícula simulada con 2 cursos y horarios mixtos."""
    buf = BytesIO()
    c = rl_canvas.Canvas(buf)
    y = 780
    for linea in [
        "UNIVERSIDAD NACIONAL MICAELA BASTIDAS DE APURIMAC",
        "CONSTANCIA DE MATRICULA 2026-II",
        "Alumno: Estudiante Uno B6    Codigo: 996001",
        "",
        "TSTOCR901 Curso de Pruebas OCR Uno          Grupo: A",
        "  LUN 10:00 - 12:00        MIE 10:00 - 12:00",
        "",
        "TSTOCR902 Curso de Pruebas OCR Dos          Grupo: B",
        "  MAR 14:00-16:00",
        "  VIE 18:00 - 20:00",
    ]:
        c.drawString(60, y, linea)
        y -= 22
    c.save()
    return buf.getvalue()


def _pdf_escaneado() -> bytes:
    """PDF SIN texto (solo un rectángulo): simula un escaneo de imagen."""
    buf = BytesIO()
    c = rl_canvas.Canvas(buf)
    c.setFillColorRGB(0.2, 0.4, 0.8)
    c.rect(100, 400, 300, 200, fill=1, stroke=0)
    c.save()
    return buf.getvalue()


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)
    # limpia además los cursos que pudo crear la importación
    for code in (TST_CURSO_OCR, TST_CURSO_OCR2):
        curso = (await db_session.exec(select(Course).where(Course.code == code))).first()
        if curso is not None:
            grupos = (await db_session.exec(
                select(CourseGroup).where(CourseGroup.course_id == curso.id)
            )).all()
            for g in grupos:
                await db_session.exec(
                    delete(ScheduleBlock).where(ScheduleBlock.group_id == g.id)  # type: ignore[attr-defined]
                )
                await db_session.delete(g)
            await db_session.delete(curso)
            await db_session.commit()


# ---------------------------------------------------------------------------
# Servicio puro
# ---------------------------------------------------------------------------
def test_extraer_horarios_pdf_simulado():
    bloques, paginas = extraer_horarios(_pdf_matricula())
    assert paginas == 1
    por_curso: dict[str, list] = {}
    for b in bloques:
        por_curso.setdefault(b.course_code, []).append(b)

    assert set(por_curso) == {TST_CURSO_OCR, TST_CURSO_OCR2}
    c1 = por_curso[TST_CURSO_OCR]
    assert len(c1) == 2  # LUN y MIE
    assert {b.weekday for b in c1} == {1, 3}
    assert c1[0].group_code == "A" and c1[0].confiable
    assert c1[0].start_time == "10:00" and c1[0].end_time == "12:00"
    assert "pruebas ocr uno" in (c1[0].course_name or "").lower()

    c2 = por_curso[TST_CURSO_OCR2]
    assert {(b.weekday, b.start_time, b.end_time) for b in c2} == {
        (2, "14:00", "16:00"),  # pegado sin espacios
        (5, "18:00", "20:00"),
    }
    assert all(b.group_code == "B" and b.confiable for b in c2)


def test_extraer_horarios_ambiguo():
    """Día raro y hora invertida salen con confiable=False y nota."""
    from reportlab.pdfgen import canvas as rc

    buf = BytesIO()
    c = rc.Canvas(buf)
    c.drawString(60, 780, f"{TST_CURSO_OCR} Curso Ambiguo  Grupo: A")
    c.drawString(60, 758, "LUN 10:00 - 08:00")   # invertido
    c.drawString(60, 736, "XYX 08:00 - 10:00")   # día no reconocido
    c.save()
    bloques, _ = extraer_horarios(buf.getvalue())
    assert len(bloques) == 2
    assert all(not b.confiable and b.nota for b in bloques)


def test_pdf_escaneado_sin_texto():
    bloques, paginas = extraer_horarios(_pdf_escaneado())
    assert paginas == 1 and bloques == []


# ---------------------------------------------------------------------------
# API: preview y confirmación (solo admin)
# ---------------------------------------------------------------------------
async def _subir(client, headers, pdf: bytes, filename="matricula.pdf"):
    return await client.post(
        f"{API}/courses/import-pdf", headers=headers,
        files={"file": (filename, BytesIO(pdf), "application/pdf")},
    )


async def test_preview_rechaza_no_admin(client, docente_headers, admin_headers):
    pdf = _pdf_matricula()
    r = await _subir(client, docente_headers, pdf)
    assert r.status_code == 403  # solo admin (RF-07)


async def test_preview_y_confirmacion_completa(client, admin_headers, db_session, escenario):
    esc = escenario
    r = await _subir(client, admin_headers, _pdf_matricula())
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["paginas"] == 1 and prev["total"] == 4
    assert prev["confiables"] == 4 and prev["ambiguousos"] == 0
    codes = {b["course_code"] for b in prev["bloques"]}
    assert codes == {TST_CURSO_OCR, TST_CURSO_OCR2}
    # TODOS los bloques del PDF de prueba caen en horas distintas al B6 (LUN/MIE 08-10)

    # confirmación: usa el docente y el aula del escenario B6
    bloques = [
        {"course_code": b["course_code"], "course_name": b["course_name"],
         "group_code": b["group_code"], "weekday": b["weekday"],
         "start_time": b["start_time"], "end_time": b["end_time"]}
        for b in prev["bloques"] if b["confiable"]
    ]
    r = await client.post(
        f"{API}/courses/import-pdf/confirm", headers=admin_headers,
        json={"teacher_id": esc["docente_id"], "room_id": esc["aula_id"], "bloques": bloques},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert set(data["cursos_creados"]) == {TST_CURSO_OCR, TST_CURSO_OCR2}
    assert data["grupos_creados"] == [f"{TST_CURSO_OCR}-A", f"{TST_CURSO_OCR2}-B"]
    assert data["bloques_creados"] == 4

    # la propuesta quedó EN LA BD (curso, grupos, bloques)
    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR))).first()
    assert curso is not None and "ocr uno" in curso.name.lower()
    grupo = (await db_session.exec(
        select(CourseGroup).where(
            CourseGroup.course_id == curso.id, CourseGroup.group_code == "A")  # type: ignore[arg-type]
    )).first()
    assert grupo is not None and grupo.teacher_id == esc["docente_id"]
    n_bloques = (await db_session.exec(
        select(ScheduleBlock).where(ScheduleBlock.group_id == grupo.id)  # type: ignore[attr-defined]
    )).all()
    assert len(n_bloques) == 2


async def test_confirmacion_con_choque_revierta_todo(client, admin_headers, db_session, escenario):
    """Todo o nada: un choque RF-06 revienta la propuesta COMPLETA (rollback)."""
    esc = escenario
    # bloque existente LUN 08:00-10:00 del escenario B6 (mismo aula/docente)
    bloques = [
        {"course_code": TST_CURSO_OCR, "course_name": "Choque OCR", "group_code": "A",
         "weekday": 1, "start_time": "08:00", "end_time": "10:00"},  # CHoca con el B6
        {"course_code": TST_CURSO_OCR2, "course_name": "No llega", "group_code": "B",
         "weekday": 4, "start_time": "18:00", "end_time": "20:00"},
    ]
    r = await client.post(
        f"{API}/courses/import-pdf/confirm", headers=admin_headers,
        json={"teacher_id": esc["docente_id"], "room_id": esc["aula_id"], "bloques": bloques},
    )
    assert r.status_code == 409
    # rollback: el curso del PRIMER bloque NO quedó creado
    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR))).first()
    assert curso is None


async def test_preview_escaneo_y_tamano(client, admin_headers):
    # PDF escaneado (sin texto) → 422 con explicación
    r = await _subir(client, admin_headers, _pdf_escaneado())
    assert r.status_code == 422
    assert "escaneo" in r.json()["detail"].lower()

    # archivo no-PDF → 422 del extractor
    r = await _subir(client, admin_headers, b"esto no es un pdf", filename="x.pdf")
    assert r.status_code == 422

    # vacío → 422
    r = await _subir(client, admin_headers, b"", filename="vacio.pdf")
    assert r.status_code == 422
