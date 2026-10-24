from pathlib import Path

import pytest

from app.services.ocr_extract import leer_documento
from app.services.ocr_schedule import BloqueExtraido, extraer_horarios_documento, fusionar_contiguos

FIXTURES = Path(__file__).parent / "fixtures"


def _block(start: str, end: str, **overrides) -> BloqueExtraido:
    data = {
        "course_code": "ISA901", "course_name": "Computación Gráfica", "group_code": "A", "weekday": 2,
        "room_code": "LAB 401", "teacher_name": "MAMANI VILCA, Eddy", "start_time": start, "end_time": end,
    }
    return BloqueExtraido(**{**data, **overrides})


def test_consecutive_hours_of_the_same_class_become_one_block():
    merged = fusionar_contiguos([_block("07:00", "08:00"), _block("08:00", "09:00")])

    assert [(b.start_time, b.end_time) for b in merged] == [("07:00", "09:00")]


def test_a_class_longer_than_two_hours_is_split():
    merged = fusionar_contiguos([_block("07:00", "08:00"), _block("08:00", "09:00"), _block("09:00", "10:00")])

    assert [(b.start_time, b.end_time) for b in merged] == [("07:00", "09:00"), ("09:00", "10:00")]


def test_blocks_that_differ_are_not_merged():
    other_room = fusionar_contiguos([_block("07:00", "08:00"), _block("08:00", "09:00", room_code="LAB 306")])
    other_group = fusionar_contiguos([_block("07:00", "08:00"), _block("08:00", "09:00", group_code="B")])
    gap = fusionar_contiguos([_block("07:00", "08:00"), _block("09:00", "10:00")])

    assert len(other_room) == 2 and len(other_group) == 2 and len(gap) == 2


def test_teacher_typos_from_the_ocr_do_not_prevent_the_merge():
    merged = fusionar_contiguos(
        [_block("07:00", "08:00"), _block("08:00", "09:00", teacher_name="MAMANÍ VILCA, Eddy")]
    )

    assert len(merged) == 1


@pytest.fixture(scope="module")
def table_blocks() -> list[BloqueExtraido]:
    return extraer_horarios_documento(leer_documento((FIXTURES / "horario_tabla.png").read_bytes()))


@pytest.fixture(scope="module")
def colored_blocks() -> list[BloqueExtraido]:
    return extraer_horarios_documento(leer_documento((FIXTURES / "horario_colores.png").read_bytes()))


def _find(blocks, code, weekday, start, group="A"):
    return next(b for b in blocks if b.course_code == code and b.weekday == weekday and b.start_time == start and b.group_code == group)


def test_plain_table_with_one_cell_per_hour(table_blocks):
    assert len(table_blocks) == 17
    monday = _find(table_blocks, "ISA903", 1, "07:00")
    assert monday.end_time == "09:00" and monday.room_code == "LAB 304"
    assert monday.teacher_name == "AQUINO CRUZ, Mario"
    assert _find(table_blocks, "ISA905", 1, "09:00").teacher_name.startswith("CARI INC")
    assert _find(table_blocks, "ISA904", 2, "14:00").end_time == "16:00"
    assert all(b.start_time < b.end_time for b in table_blocks)
    assert all(int(b.end_time[:2]) - int(b.start_time[:2]) <= 2 for b in table_blocks)


def test_plain_table_ignores_tutoring_and_empty_cells(table_blocks):
    assert all(b.course_code.startswith("ISA9") for b in table_blocks)
    assert {b.weekday for b in table_blocks} == {1, 2, 3, 4, 5}


def test_colored_table_with_merged_cells_and_two_groups(colored_blocks):
    assert len(colored_blocks) == 26
    history = _find(colored_blocks, "AGG3", 2, "07:00")
    assert history.end_time == "09:00" and history.room_code == "AULA 104"
    math_a = _find(colored_blocks, "AGG2", 3, "07:00", "A")
    math_b = _find(colored_blocks, "AGG2", 3, "07:00", "B")
    assert (math_a.room_code, math_b.room_code) == ("AULA 103", "AULA 104")
    drawing = _find(colored_blocks, "AGG19", 2, "09:00", "A")
    assert drawing.teacher_name.startswith("FUENTES") and drawing.room_code == "LAB 206"
    assert _find(colored_blocks, "AGG1", 2, "16:00").end_time == "18:00"


def test_colored_table_does_not_invent_courses_from_tutoring(colored_blocks):
    assert not any("TUTOR" in (b.course_name or "").upper() for b in colored_blocks)
    assert {b.course_code for b in colored_blocks} == {"AGG1", "AGG2", "AGG3", "AGG4", "AGG6", "AGG7", "AGG19", "AIS11"}
