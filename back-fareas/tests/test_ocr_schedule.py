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
    for code in (TST_CURSO_OCR, TST_CURSO_OCR2):
        curso = (await db_session.exec(select(Course).where(Course.code == code))).first()
        if curso is not None:
            grupos = (await db_session.exec(
                select(CourseGroup).where(CourseGroup.course_id == curso.id)
            )).all()
            for g in grupos:
                await db_session.exec(
                    delete(ScheduleBlock).where(ScheduleBlock.group_id == g.id)
                )
                await db_session.delete(g)
            await db_session.delete(curso)
            await db_session.commit()

def test_extraer_horarios_pdf_simulado():
    bloques, paginas = extraer_horarios(_pdf_matricula())
    assert paginas == 1
    por_curso: dict[str, list] = {}
    for b in bloques:
        por_curso.setdefault(b.course_code, []).append(b)

    assert set(por_curso) == {TST_CURSO_OCR, TST_CURSO_OCR2}
    c1 = por_curso[TST_CURSO_OCR]
    assert len(c1) == 2
    assert {b.weekday for b in c1} == {1, 3}
    assert c1[0].group_code == "A" and c1[0].confiable
    assert c1[0].start_time == "10:00" and c1[0].end_time == "12:00"
    assert "pruebas ocr uno" in (c1[0].course_name or "").lower()

    c2 = por_curso[TST_CURSO_OCR2]
    assert {(b.weekday, b.start_time, b.end_time) for b in c2} == {
        (2, "14:00", "16:00"),
        (5, "18:00", "20:00"),
    }
    assert all(b.group_code == "B" and b.confiable for b in c2)

def test_extraer_horarios_ambiguo():
    from reportlab.pdfgen import canvas as rc

    buf = BytesIO()
    c = rc.Canvas(buf)
    c.drawString(60, 780, f"{TST_CURSO_OCR} Curso Ambiguo  Grupo: A")
    c.drawString(60, 758, "LUN 10:00 - 08:00")
    c.drawString(60, 736, "XYX 08:00 - 10:00")
    c.save()
    bloques, _ = extraer_horarios(buf.getvalue())
    assert len(bloques) == 2
    assert all(not b.confiable and b.nota for b in bloques)

def test_pdf_escaneado_sin_texto():
    bloques, paginas = extraer_horarios(_pdf_escaneado())
    assert paginas == 1 and bloques == []

async def _subir(client, headers, pdf: bytes, filename="matricula.pdf"):
    return await client.post(
        f"{API}/courses/import-pdf", headers=headers,
        files={"file": (filename, BytesIO(pdf), "application/pdf")},
    )

async def test_preview_rechaza_no_admin(client, docente_headers, admin_headers):
    pdf = _pdf_matricula()
    r = await _subir(client, docente_headers, pdf)
    assert r.status_code == 403

async def test_preview_y_confirmacion_completa(client, admin_headers, db_session, escenario):
    esc = escenario
    r = await _subir(client, admin_headers, _pdf_matricula())
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["paginas"] == 1 and prev["total"] == 4
    assert prev["confiables"] == 4 and prev["ambiguousos"] == 0
    codes = {b["course_code"] for b in prev["bloques"]}
    assert codes == {TST_CURSO_OCR, TST_CURSO_OCR2}

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

    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR))).first()
    assert curso is not None and "ocr uno" in curso.name.lower()
    grupo = (await db_session.exec(
        select(CourseGroup).where(
            CourseGroup.course_id == curso.id, CourseGroup.group_code == "A")
    )).first()
    assert grupo is not None and grupo.teacher_id == esc["docente_id"]
    n_bloques = (await db_session.exec(
        select(ScheduleBlock).where(ScheduleBlock.group_id == grupo.id)
    )).all()
    assert len(n_bloques) == 2

async def test_confirmacion_con_choque_revierta_todo(client, admin_headers, db_session, escenario):
    esc = escenario
    bloques = [
        {"course_code": TST_CURSO_OCR, "course_name": "Choque OCR", "group_code": "A",
         "weekday": 1, "start_time": "08:00", "end_time": "10:00"},
        {"course_code": TST_CURSO_OCR2, "course_name": "No llega", "group_code": "B",
         "weekday": 4, "start_time": "18:00", "end_time": "20:00"},
    ]
    r = await client.post(
        f"{API}/courses/import-pdf/confirm", headers=admin_headers,
        json={"teacher_id": esc["docente_id"], "room_id": esc["aula_id"], "bloques": bloques},
    )
    assert r.status_code == 409
    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR))).first()
    assert curso is None

async def test_preview_escaneo_y_tamano(client, admin_headers):
    r = await _subir(client, admin_headers, _pdf_escaneado())
    assert r.status_code == 422
    assert "escaneo" in r.json()["detail"].lower()

    r = await _subir(client, admin_headers, b"esto no es un pdf", filename="x.pdf")
    assert r.status_code == 422

    r = await _subir(client, admin_headers, b"", filename="vacio.pdf")
    assert r.status_code == 422
