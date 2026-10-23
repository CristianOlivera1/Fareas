from io import BytesIO

import pytest
from reportlab.pdfgen import canvas as rl_canvas
from sqlmodel import delete, select

from app.services.import_matching import emparejar_aula, emparejar_docente, sugerir_curso
from app.services.ocr_extract import DocumentoLeido, ItemTexto
from app.services.ocr_schedule import extraer_horarios, extraer_horarios_documento
from app.tables import AppUser, Course, CourseGroup, Room, ScheduleBlock, UserRole
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"
TST_CURSO_OCR = "TSTOCR901"
TST_CURSO_OCR2 = "TSTOCR902"
TST_CURSO_OCR3 = "TSTOCR903"


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
    for code in (TST_CURSO_OCR, TST_CURSO_OCR2, TST_CURSO_OCR3):
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

def _item(
    texto: str, x: float, y: float, ancho: float, alto: float = 20.0, confianza: float = 0.99
) -> ItemTexto:
    return ItemTexto(
        texto=texto, x=x, y=y, ancho=ancho, alto=alto, confianza=confianza, pagina=1
    )


def test_extraer_horarios_tabla_por_columnas():
    items = [
        _item("GRUPO A", 9, 10, 60),
        _item("Lunes", 220, 30, 60),
        _item("Martes", 470, 30, 60),
        _item("Miércoles", 720, 30, 78),
        _item("Jueves", 960, 30, 60),
        _item("Viernes", 1150, 30, 65),
        _item("07:00 - 08:00", 9, 110, 95),
        _item("ISA903 Inteligencia Artificial I (LAB 304)", 105, 90, 260),
        _item("AQUINO CRUZ, Mario (Mag.)", 105, 110, 200),
        _item("ISA901 Computación Gráfica", 390, 75, 190),
        _item("(LAB 401)", 390, 95, 70),
        _item("MAMANI VILCA, Eddy (Dr.)", 390, 110, 180),
        _item("ISA903 Inteligencia Artificial I (LAB 304)", 610, 90, 260),
        _item("AQUINO CRUZ, Mario (Mag.)", 610, 110, 200),
        _item("ISA901 Computación", 890, 60, 150),
        _item("Gráfica (LAB 401)", 890, 80, 130),
        _item("MAMANI VILCA, Eddy", 890, 100, 155),
        _item("(Dr.)", 890, 115, 38),
        _item("ISA904 Programación Paralela", 1070, 90, 200),
        _item("(LAB 304)", 1070, 110, 70),
        _item("08:00 - 09:00", 9, 190, 95),
        _item("ISA905 Metodología de la Investigación Científica (LAB 305)", 105, 170, 260),
        _item("CARI INCAHUANACO, Francisco (Mag.)", 105, 190, 260),
        _item("Tutoría", 390, 170, 60),
        _item("09:00 - 10:00", 9, 280, 95),
        _item("ISA906 Interacción Humano Computador (LAB 304)", 610, 260, 260),
        _item("ROJAS ENRIQUEZ, Hermenegildo (Dr.)", 610, 280, 260),
    ]
    documento = DocumentoLeido(tipo="imagen", paginas=1, items=items, lineas=[])
    bloques = extraer_horarios_documento(documento)

    assert len(bloques) == 7
    assert all(bloque.group_code == "A" and bloque.confiable for bloque in bloques)
    assert all(bloque.nota is None for bloque in bloques)
    assert {(b.weekday, b.course_code) for b in bloques} == {
        (1, "ISA903"),
        (2, "ISA901"),
        (3, "ISA903"),
        (4, "ISA901"),
        (5, "ISA904"),
        (1, "ISA905"),
        (3, "ISA906"),
    }
    por_curso = {bloque.course_code: bloque for bloque in bloques}
    assert por_curso["ISA903"].course_name == "Inteligencia Artificial I"
    assert por_curso["ISA903"].teacher_name == "AQUINO CRUZ, Mario"
    assert por_curso["ISA903"].room_code == "LAB 304"
    assert por_curso["ISA901"].course_name == "Computación Gráfica"
    assert por_curso["ISA901"].teacher_name == "MAMANI VILCA, Eddy"
    assert por_curso["ISA901"].room_code == "LAB 401"
    assert por_curso["ISA906"].start_time == "09:00"
    assert por_curso["ISA906"].end_time == "10:00"
    assert por_curso["ISA906"].teacher_name == "ROJAS ENRIQUEZ, Hermenegildo"
    assert por_curso["ISA906"].room_code == "LAB 304"


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
        json={"teacher_id": esc["docente_id"], "room_id": esc["aula_id"],
              "cycle": 9, "bloques": bloques},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert set(data["cursos_creados"]) == {TST_CURSO_OCR, TST_CURSO_OCR2}
    assert data["grupos_creados"] == [f"{TST_CURSO_OCR}-A", f"{TST_CURSO_OCR2}-B"]
    assert data["bloques_creados"] == 4

    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR))).first()
    assert curso is not None and "ocr uno" in curso.name.lower()
    assert curso.cycle == 9
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
        json={"teacher_id": esc["docente_id"], "room_id": esc["aula_id"],
              "cycle": 9, "bloques": bloques},
    )
    assert r.status_code == 409
    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR))).first()
    assert curso is None

def test_coincidencias_para_autocompletar():
    cursos = [
        Course(id=1, code="ISA903", name="Inteligencia Artificial I", cycle=9),
        Course(id=2, code="ISA901", name="Computación Gráfica", cycle=9),
    ]
    sugerido = sugerir_curso("ISA9O3", "INTELIGENCIA ARTIFICIAL I", cursos)
    assert sugerido is not None and sugerido.valor.code == "ISA903"
    assert sugerir_curso("ISA904", "PROGRAMACION PARALELA", cursos) is None

    docentes = [
        AppUser(id=3, role=UserRole.DOCENTE, email="mamani@test.pe",
                full_name="Eddy Mamani Vilca", password_hash="x" * 20),
        AppUser(id=4, role=UserRole.DOCENTE, email="aquino@test.pe",
                full_name="Mario Aquino Cruz", password_hash="x" * 20),
    ]
    docente = emparejar_docente("MAMANI VILCA, Eddy (Dr.)", docentes)
    assert docente is not None and docente.valor.id == 3
    assert emparejar_docente("VILCA, Eddy", docentes).valor.id == 3
    assert emparejar_docente("QUINO CRUZ, Mario", docentes).valor.id == 4

    aulas = [Room(id=7, code="LAB 401"), Room(id=8, code="LAB 304")]
    aula = emparejar_aula("LAB 401", aulas)
    assert aula is not None and aula.valor.id == 7

async def test_confirmacion_sin_docente_ni_aula(client, admin_headers, db_session, escenario):
    payload = {
        "cycle": 9, "semester_label": "2027-I",
        "bloques": [
            {"course_code": TST_CURSO_OCR3, "course_name": "Curso sin docente",
             "group_code": "A", "weekday": 1, "start_time": "07:00", "end_time": "09:00"},
        ],
    }
    r = await client.post(
        f"{API}/courses/import-pdf/confirm", headers=admin_headers, json=payload
    )
    assert r.status_code == 201, r.text

    curso = (await db_session.exec(select(Course).where(Course.code == TST_CURSO_OCR3))).first()
    assert curso is not None
    grupo = (await db_session.exec(
        select(CourseGroup).where(CourseGroup.course_id == curso.id)
    )).first()
    assert grupo is not None and grupo.teacher_id is None
    bloque = (await db_session.exec(
        select(ScheduleBlock).where(ScheduleBlock.group_id == grupo.id)
    )).first()
    assert bloque is not None and bloque.room_id is None

    r = await client.get(
        f"{API}/schedule", headers=admin_headers, params={"semester": "2027-I"}
    )
    assert r.status_code == 200, r.text
    fila = next(f for f in r.json() if f["id"] == bloque.id)
    assert fila["teacher_id"] is None and fila["room_id"] is None
    assert fila["teacher_name"] is None and fila["room_code"] is None

    r = await client.patch(
        f"{API}/blocks/{bloque.id}", headers=admin_headers,
        json={"teacher_id": escenario["docente_id"], "room_id": escenario["aula_id"]},
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(grupo)
    await db_session.refresh(bloque)
    assert grupo.teacher_id == escenario["docente_id"]
    assert bloque.room_id == escenario["aula_id"]

async def test_preview_escaneo_y_tamano(client, admin_headers):
    r = await _subir(client, admin_headers, _pdf_escaneado())
    assert r.status_code == 422
    assert "reconocieron" in r.json()["detail"].lower()

    r = await _subir(client, admin_headers, b"esto no es un pdf", filename="x.pdf")
    assert r.status_code == 415

    r = await _subir(client, admin_headers, b"", filename="vacio.pdf")
    assert r.status_code == 422
