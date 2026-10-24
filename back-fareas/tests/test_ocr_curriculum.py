from collections import Counter
from pathlib import Path

import pytest
from sqlmodel import delete

from app.services.ocr_curriculum import cycle_from_text, extraer_malla_documento
from app.services.ocr_extract import DocumentoLeido, ItemTexto, leer_documento
from app.tables import Course

API = "/api/v1"
FIXTURE = Path(__file__).parent / "fixtures" / "malla_ais.png"
TEST_CODES = ("TSTMAL1", "TSTMAL2", "TSTMAL3")


def _item(text: str, x: float, y: float, w: float = 80, h: float = 18, conf: float = 1.0, page: int = 1) -> ItemTexto:
    return ItemTexto(texto=text, x=x, y=y, ancho=w, alto=h, confianza=conf, pagina=page)


def _doc(items: list[ItemTexto]) -> DocumentoLeido:
    return DocumentoLeido(tipo="imagen", paginas=1, items=items, lineas=[])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PRIMER CICLO", 1),
        ("SÉPTIMO CICLO", 7),
        ("DÉCIMO CICLO", 10),
        ("Ciclo IV", 4),
        ("CICLO 9", 9),
        ("III CICLO", 3),
        ("2° CICLO", 2),
        ("Introducción a la informática", None),
        ("CICLO 11", None),
    ],
)
def test_cycle_headers_are_recognized(text, expected):
    assert cycle_from_text(text) == expected


def _three_columns() -> list[ItemTexto]:
    return [
        _item("PRIMER CICLO", 20, 10),
        _item("SEGUNDO CICLO", 220, 10),
        _item("TERCER CICLO", 420, 10),
        _item("Cálculo", 30, 70),
        _item("AAA11", 40, 120, w=50, h=22),
        _item("Física", 230, 70),
        _item("I", 260, 88, w=8),
        _item("AAA21", 240, 120, w=50, h=22),
        _item("Robótica", 430, 70),
        _item("(Electivo)", 430, 88),
        _item("AAA31", 440, 120, w=50, h=22),
        _item("0", 330, 100, w=10, conf=0.62),
        _item("Álgebra", 30, 200),
        _item("AAA12", 40, 240, w=50, h=22),
    ]


def test_columns_assign_cycle_and_join_multiline_names():
    courses = extraer_malla_documento(_doc(_three_columns()))

    by_code = {course.code: course for course in courses}
    assert by_code["AAA11"].cycle == 1 and by_code["AAA11"].name == "Cálculo"
    assert by_code["AAA12"].cycle == 1 and by_code["AAA12"].name == "Álgebra"
    assert by_code["AAA21"].cycle == 2 and by_code["AAA21"].name == "Física I"
    assert by_code["AAA31"].cycle == 3 and by_code["AAA31"].name == "Robótica (Electivo)"
    assert all(course.confiable for course in courses)


def test_arrow_noise_is_ignored():
    courses = extraer_malla_documento(_doc(_three_columns()))

    assert all("0" not in course.name for course in courses)


def test_low_confidence_and_missing_name_are_flagged():
    items = _three_columns()
    items.append(_item("AAA13", 40, 330, w=50, h=22))
    items.append(_item("Estadística", 30, 280, conf=0.7))
    items.append(_item("AAA14", 40, 420, w=50, h=22))
    courses = {course.code: course for course in extraer_malla_documento(_doc(items))}

    assert courses["AAA13"].confiable is False and "poca confianza" in courses["AAA13"].nota
    assert courses["AAA14"].confiable is False and "nombre" in courses["AAA14"].nota


def test_duplicate_codes_are_flagged():
    items = _three_columns()
    items.append(_item("Repetido", 30, 280))
    items.append(_item("AAA11", 40, 330, w=50, h=22))
    duplicates = [c for c in extraer_malla_documento(_doc(items)) if c.code == "AAA11"]

    assert len(duplicates) == 2
    assert all(not c.confiable and "repetido" in c.nota for c in duplicates)


def test_without_headers_cycles_follow_the_columns_and_are_flagged():
    items = [i for i in _three_columns() if not i.texto.endswith("CICLO")]
    courses = {course.code: course for course in extraer_malla_documento(_doc(items))}

    assert [courses[c].cycle for c in ("AAA11", "AAA21", "AAA31")] == [1, 2, 3]
    assert all(not course.confiable for course in courses.values())


def test_vertical_list_with_cycle_titles():
    items = [
        _item("PRIMER CICLO", 20, 10, w=120),
        _item("AIS11", 20, 50, w=50), _item("Introducción a la informática", 100, 50, w=250),
        _item("AGG1", 20, 80, w=50), _item("Lengua castellana", 100, 80, w=200),
        _item("SEGUNDO CICLO", 20, 140, w=120),
        _item("AIS21", 20, 180, w=50), _item("Análisis y diseño", 100, 180, w=200),
        _item("de sistemas", 100, 198, w=120),
    ]
    courses = {course.code: course for course in extraer_malla_documento(_doc(items))}

    assert courses["AIS11"].cycle == 1 and courses["AIS11"].name == "Introducción a la informática"
    assert courses["AIS21"].cycle == 2 and courses["AIS21"].name == "Análisis y diseño de sistemas"


def test_a_list_without_titles_uses_the_default_cycle():
    items = [_item("AIS11", 20, 50, w=50), _item("Introducción", 100, 50), _item("AIS12", 20, 90, w=50), _item("Cálculo", 100, 90)]

    without_cycle = extraer_malla_documento(_doc(items))
    assert {course.cycle for course in without_cycle} == {None}
    assert all(not course.confiable and "ciclo" in course.nota.lower() for course in without_cycle)

    courses = extraer_malla_documento(_doc(items), default_cycle=4)
    assert {course.cycle for course in courses} == {4}
    assert all(course.confiable for course in courses)


def test_real_curriculum_image_is_read_completely():
    document = leer_documento(FIXTURE.read_bytes())
    courses = extraer_malla_documento(document)

    assert len(courses) == 63
    assert [Counter(c.cycle for c in courses)[cycle] for cycle in range(1, 11)] == [7, 6, 6, 6, 6, 6, 7, 7, 6, 6]
    by_code = {course.code: course for course in courses}
    assert by_code["AIS73"].name == "Ingeniería de software II" and by_code["AIS73"].cycle == 7
    assert by_code["AGG20"].name == "Física I" and by_code["AGG20"].cycle == 2
    assert by_code["AIS04"].cycle == 10 and "innovación" in by_code["AIS04"].name
    assert by_code["AIS77"].name == "Redacción de artículos cientificos (Electivo)"
    assert by_code["AIS63"].name == "Gerencia de proyectos de tecnologías de información"
    assert sum(1 for course in courses if not course.confiable) <= 3


@pytest.fixture
async def clean_courses(db_session):
    await db_session.exec(delete(Course).where(Course.code.in_(TEST_CODES)))
    await db_session.commit()
    yield
    await db_session.exec(delete(Course).where(Course.code.in_(TEST_CODES)))
    await db_session.commit()


async def test_preview_endpoint_returns_editable_rows(client, admin_headers):
    r = await client.post(
        f"{API}/courses/import-curriculum",
        headers=admin_headers,
        files={"file": ("malla.png", FIXTURE.read_bytes(), "image/png")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tipo"] == "imagen" and data["total"] == 63 and data["ciclos"] == list(range(1, 11))
    first = data["cursos"][0]
    assert {"fila", "code", "name", "cycle", "confiable", "nota", "linea", "ya_existe"} <= first.keys()


async def test_preview_requires_admin_and_a_valid_file(client, admin_headers, docente_headers):
    files = {"file": ("malla.png", FIXTURE.read_bytes(), "image/png")}
    assert (await client.post(f"{API}/courses/import-curriculum", headers=docente_headers, files=files)).status_code == 403

    empty = await client.post(
        f"{API}/courses/import-curriculum", headers=admin_headers, files={"file": ("x.png", b"", "image/png")}
    )
    assert empty.status_code == 422

    text = await client.post(
        f"{API}/courses/import-curriculum", headers=admin_headers, files={"file": ("x.txt", b"hola", "text/plain")}
    )
    assert text.status_code == 415


async def test_confirm_creates_new_courses_and_skips_existing(client, admin_headers, clean_courses):
    body = {"cursos": [
        {"code": "tstmal1", "name": "  Curso   de  prueba uno ", "cycle": 1},
        {"code": "TSTMAL2", "name": "Curso de prueba dos", "cycle": 10},
    ]}
    r = await client.post(f"{API}/courses/import-curriculum/confirm", headers=admin_headers, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["creados"] == 2 and r.json()["codigos_creados"] == ["TSTMAL1", "TSTMAL2"]

    listed = await client.get(f"{API}/courses?q=TSTMAL1", headers=admin_headers)
    assert listed.json()["items"][0]["name"] == "Curso de prueba uno"

    again = await client.post(f"{API}/courses/import-curriculum/confirm", headers=admin_headers, json=body)
    assert again.json()["creados"] == 0 and again.json()["omitidos"] == 2


async def test_confirm_rejects_repeated_codes_and_invalid_cycles(client, admin_headers, clean_courses):
    repeated = {"cursos": [
        {"code": "TSTMAL3", "name": "Uno", "cycle": 1},
        {"code": "TSTMAL3", "name": "Dos", "cycle": 2},
    ]}
    r = await client.post(f"{API}/courses/import-curriculum/confirm", headers=admin_headers, json=repeated)
    assert r.status_code == 422 and "TSTMAL3" in r.json()["detail"]

    bad_cycle = {"cursos": [{"code": "TSTMAL3", "name": "Curso válido", "cycle": 11}]}
    assert (await client.post(f"{API}/courses/import-curriculum/confirm", headers=admin_headers, json=bad_cycle)).status_code == 422


async def test_confirm_requires_admin(client, docente_headers):
    r = await client.post(
        f"{API}/courses/import-curriculum/confirm",
        headers=docente_headers,
        json={"cursos": [{"code": "TSTMAL3", "name": "Curso válido", "cycle": 1}]},
    )
    assert r.status_code == 403


def _text_pdf() -> bytes:
    from io import BytesIO

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    columns = [("PRIMER CICLO", 60), ("SEGUNDO CICLO", 300), ("TERCER CICLO", 540)]
    for title, x in columns:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x, height - 40, title)
    rows = [
        (60, "Introduccion a la", "informatica", "AIS11"),
        (300, "Analisis y diseno de", "sistemas", "AIS21"),
        (540, "Matematica discreta I", "", "AIS31"),
    ]
    pdf.setFont("Helvetica", 10)
    for x, first, second, code in rows:
        pdf.drawString(x, height - 100, first)
        if second:
            pdf.drawString(x, height - 114, second)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x, height - 140, code)
        pdf.setFont("Helvetica", 10)
    pdf.save()
    return buffer.getvalue()


def test_text_pdf_with_split_headers_is_parsed_without_ocr():
    document = leer_documento(_text_pdf())

    assert document.tipo == "pdf_texto"
    courses = {course.code: course for course in extraer_malla_documento(document)}
    assert courses["AIS11"].cycle == 1 and courses["AIS11"].name == "Introduccion a la informatica"
    assert courses["AIS21"].cycle == 2 and courses["AIS21"].name == "Analisis y diseno de sistemas"
    assert courses["AIS31"].cycle == 3 and courses["AIS31"].name == "Matematica discreta I"
