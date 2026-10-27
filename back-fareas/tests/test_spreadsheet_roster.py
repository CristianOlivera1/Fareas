import io

import pytest
from openpyxl import Workbook

from app.services.spreadsheet_roster import read_spreadsheet


def _xlsx(rows: list[list], extra_sheets: list[list[list]] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    for more in extra_sheets or []:
        other = workbook.create_sheet()
        for row in more:
            other.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _read(raw: bytes, name: str = "alumnos.xlsx", semester: int = 3):
    return read_spreadsheet(raw, name, default_semester=semester)


def test_classroom_export_without_headers_or_dni():
    rows = [
        ["Formulación de proyectos informáticos", "", "", "", "06 oct"],
        ["2026-2AIS35-", "", "", "", "Tarea: Pila del producto"],
        ["ABRIR CLASSROOM", "", "", "", 100.0],
        [],
        ["Media de la clase", "", "", None, None],
        ["Ticona Ortiz", "Abril Yady", "252188@unamba.edu.pe", None, None],
        ["Sota Bazan", "Anderson Alain", "252187@unamba.edu.pe", None, None],
    ]
    result = _read(_xlsx(rows))

    assert result.kind == "xlsx"
    assert [(s.code, s.full_name, s.email, s.dni) for s in result.students] == [
        ("252188", "Ticona Ortiz, Abril Yady", "252188@unamba.edu.pe", None),
        ("252187", "Sota Bazan, Anderson Alain", "252187@unamba.edu.pe", None),
    ]
    assert all(s.semester == 3 and not s.errores for s in result.students)


def test_labelled_columns_in_any_order_with_numeric_cells():
    rows = [
        ["Lista de estudiantes"],
        ["Nro", "Ciclo", "DNI", "Código", "Apellidos y Nombres", "Celular", "Correo"],
        [1, "IV", 71234567, 221181, "Quispe Mamani, Juan", 987654321, "221181@unamba.edu.pe"],
        [2, 5, 7123456, 221182, "Huamán Ccori, Ana", "+51 912 345 678", None],
    ]
    first, second = _read(_xlsx(rows)).students

    assert (first.code, first.dni, first.semester, first.whatsapp) == ("221181", "71234567", 4, "987654321")
    assert first.full_name == "Quispe Mamani, Juan"
    assert (second.dni, second.semester, second.whatsapp) == ("07123456", 5, "912345678")
    assert second.email == "221182@unamba.edu.pe" and second.email_generado


def test_split_surname_columns_and_missing_dni_is_optional():
    rows = [
        ["Código", "Ap. Paterno", "Ap. Materno", "Nombres"],
        ["221181", "Quispe", "Mamani", "Juan Carlos"],
    ]
    student = _read(_xlsx(rows)).students[0]

    assert student.full_name == "Quispe Mamani, Juan Carlos"
    assert student.dni is None and not student.errores


def test_headerless_sheet_infers_columns_from_content():
    rows = [
        ["221181", "71234567", "Quispe Mamani", "Juan", "987654321", "VI"],
        ["221182", "71234568", "Huamán Ccori", "Ana", "912345678", "VI"],
    ]
    student = _read(_xlsx(rows)).students[1]

    assert (student.code, student.dni, student.whatsapp, student.semester) == (
        "221182", "71234568", "912345678", 6,
    )
    assert student.full_name == "Huamán Ccori, Ana"


def test_invalid_dni_is_reported_but_blank_is_not():
    rows = [
        ["Código", "DNI", "Nombre completo"],
        ["221181", "1234", "Quispe Mamani, Juan"],
        ["221182", "", "Huamán Ccori, Ana"],
    ]
    bad, blank = _read(_xlsx(rows)).students

    assert "El DNI debe tener 8 dígitos" in bad.errores
    assert not blank.errores


def test_duplicates_inside_the_file_and_extra_sheets():
    rows = [["Código", "Nombre"], ["221181", "Quispe Mamani, Juan"]]
    more = [["Código", "Nombre"], ["221181", "Quispe Mamani, Juan"], ["221183", "Perez Soto, Luis"]]
    result = _read(_xlsx(rows, [more]))

    assert result.sheets == 2 and len(result.students) == 3
    assert any("repetido" in e for e in result.students[1].errores)
    assert not result.students[2].errores


def test_csv_with_semicolons_and_latin1_encoding():
    text = "Código;Apellidos;Nombres;Correo\n221181;Núñez Soto;José;221181@unamba.edu.pe\n"
    student = _read(text.encode("cp1252"), "alumnos.csv").students[0]

    assert student.full_name == "Núñez Soto, José"
    assert student.email == "221181@unamba.edu.pe"


def test_xls_is_rejected_with_a_helpful_message():
    with pytest.raises(ValueError, match="Formato no soportado"):
        read_spreadsheet(b"\xd0\xcf\x11\xe0rest", "viejo.xls", default_semester=1)


def test_sheet_without_student_rows_returns_nothing():
    assert _read(_xlsx([["Título"], ["sin datos"]])).students == []
