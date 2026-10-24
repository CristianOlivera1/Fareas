from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from statistics import median

from app.services.ocr_extract import DocumentoLeido, ItemTexto, agrupar_filas

ORDINALS = {
    "PRIMER": 1, "PRIMERO": 1, "SEGUNDO": 2, "TERCER": 3, "TERCERO": 3, "CUARTO": 4,
    "QUINTO": 5, "SEXTO": 6, "SEPTIMO": 7, "OCTAVO": 8, "NOVENO": 9, "DECIMO": 10,
}
ROMANS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
CYCLE_WORD = r"(?:CICLO|SEMESTRE)"
SPANISH_SINGLE_LETTERS = {"A", "E", "O", "U", "Y"}
CODE_PATTERN = re.compile(r"^[A-Z]{2,5}\d{1,3}$")

MIN_ITEM_CONFIDENCE = 0.5
RELIABLE_CONFIDENCE = 0.85
MAX_NAME_HEIGHTS = 6.0
MAX_NAME_LENGTH = 160


@dataclass(slots=True)
class CursoExtraido:
    code: str
    name: str
    cycle: int | None
    confiable: bool
    nota: str | None
    linea: str
    pagina: int
    ciclo_detectado: bool = True


@dataclass(slots=True)
class _Header:
    cycle: int
    x: float
    y: float
    bottom: float


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).upper().strip()


def _clean_header_text(text: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", " ", _plain(text)).replace("  ", " ").strip()


def cycle_from_text(text: str) -> int | None:
    value = " ".join(_clean_header_text(text).split())
    ordinal = re.fullmatch(rf"([A-Z]+) {CYCLE_WORD}", value)
    if ordinal and ordinal.group(1) in ORDINALS:
        return ORDINALS[ordinal.group(1)]
    after = re.fullmatch(rf"{CYCLE_WORD} ([A-Z0-9]+)", value)
    before = re.fullmatch(rf"([A-Z0-9]+) {CYCLE_WORD}", value)
    token = (after or before).group(1) if (after or before) else None
    if token is None:
        return None
    if token.isdigit():
        number = int(token)
        return number if 1 <= number <= 10 else None
    return ROMANS.get(token)


def _normalize_code(text: str) -> str | None:
    compact = re.sub(r"[\s\-_.]", "", text.upper())
    return compact if CODE_PATTERN.fullmatch(compact) and len(compact) >= 3 else None


def _looks_like_name_part(item: ItemTexto) -> bool:
    text = item.texto.strip()
    if item.confianza < MIN_ITEM_CONFIDENCE:
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    if len(text) < 2 and text.upper() not in ROMANS and text.upper() not in SPANISH_SINGLE_LETTERS:
        return False
    return True


def _merge_header_words(items: list[ItemTexto]) -> list[ItemTexto]:
    merged: list[ItemTexto] = []
    ordered = sorted(items, key=lambda item: (item.pagina, item.y, item.x))
    used: set[int] = set()
    for index, first in enumerate(ordered):
        if index in used:
            continue
        current = first
        for other_index in range(index + 1, len(ordered)):
            other = ordered[other_index]
            if other_index in used or other.pagina != current.pagina:
                continue
            same_row = abs((other.y + other.alto / 2) - (current.y + current.alto / 2)) <= max(current.alto, 6)
            gap = other.x - (current.x + current.ancho)
            if same_row and 0 <= gap <= max(current.alto * 1.2, 8):
                current = ItemTexto(
                    texto=f"{current.texto} {other.texto}",
                    x=current.x,
                    y=min(current.y, other.y),
                    ancho=other.x + other.ancho - current.x,
                    alto=max(current.alto, other.alto),
                    confianza=min(current.confianza, other.confianza),
                    pagina=current.pagina,
                )
                used.add(other_index)
        merged.append(current)
    return merged


def _find_headers(items: list[ItemTexto]) -> list[_Header]:
    found: dict[int, _Header] = {}
    for item in [*items, *_merge_header_words(items)]:
        cycle = cycle_from_text(item.texto)
        if cycle is None or cycle in found:
            continue
        found[cycle] = _Header(cycle, item.x + item.ancho / 2, item.y, item.y + item.alto)
    return sorted(found.values(), key=lambda header: header.x)


def _is_column_layout(headers: list[_Header]) -> bool:
    if len(headers) < 2:
        return False
    ys = [header.y for header in headers]
    heights = [header.bottom - header.y for header in headers]
    return max(ys) - min(ys) <= max(median(heights) * 3, 20)


def _column_of(x: float, headers: list[_Header]) -> int:
    centers = [header.x for header in headers]
    return min(range(len(centers)), key=lambda index: abs(centers[index] - x))


def _join_name(parts: list[ItemTexto]) -> str:
    if not parts:
        return ""
    tolerance = max(median([part.alto for part in parts]) * 0.6, 4.0)
    ordered = sorted(parts, key=lambda part: part.y + part.alto / 2)
    lines: list[list[ItemTexto]] = [[ordered[0]]]
    for part in ordered[1:]:
        reference = lines[-1][0]
        if abs((part.y + part.alto / 2) - (reference.y + reference.alto / 2)) <= tolerance:
            lines[-1].append(part)
        else:
            lines.append([part])
    text = " ".join(
        part.texto.strip() for line in lines for part in sorted(line, key=lambda part: part.x)
    )
    text = re.sub(r"\s+", " ", text).strip(" -–—,.;:")
    return text[:MAX_NAME_LENGTH]


def _finish(
    code_item: ItemTexto,
    code: str,
    name_items: list[ItemTexto],
    cycle: int | None,
    detected: bool,
    extra_notes: list[str],
) -> CursoExtraido:
    name = _join_name(name_items)
    notes = list(extra_notes)
    confidences = [code_item.confianza, *[item.confianza for item in name_items]]
    if not name:
        notes.append("No se leyó el nombre del curso")
    elif sum(ch.isalpha() for ch in name) < 3:
        notes.append("El nombre parece incompleto")
    if min(confidences) < RELIABLE_CONFIDENCE:
        notes.append("Lectura con poca confianza; verifica el texto")
    if not detected:
        notes.append("Ciclo asignado por posición; verifícalo")
    line = " ".join([name, code]).strip()
    return CursoExtraido(
        code=code,
        name=name,
        cycle=cycle,
        confiable=not notes,
        nota="; ".join(notes) or None,
        linea=line,
        pagina=code_item.pagina,
        ciclo_detectado=detected,
    )


def _extract_columns(
    items: list[ItemTexto], headers: list[_Header]
) -> list[CursoExtraido]:
    codes: list[tuple[ItemTexto, str]] = []
    others: list[ItemTexto] = []
    header_bottom = max(header.bottom for header in headers)
    for item in items:
        if item.y < header_bottom - 2:
            continue
        code = _normalize_code(item.texto)
        if code is not None:
            codes.append((item, code))
        elif _looks_like_name_part(item):
            others.append(item)

    code_height = median([item.alto for item, _ in codes]) if codes else 20.0
    by_column: dict[int, list[tuple[ItemTexto, str]]] = {}
    for item, code in codes:
        by_column.setdefault(_column_of(item.x + item.ancho / 2, headers), []).append((item, code))

    result: list[CursoExtraido] = []
    for column, entries in by_column.items():
        entries.sort(key=lambda entry: entry[0].y)
        column_items = [
            item for item in others if _column_of(item.x + item.ancho / 2, headers) == column
        ]
        previous_bottom = header_bottom
        for item, code in entries:
            limit = item.y - code_height * MAX_NAME_HEIGHTS
            names = [
                part for part in column_items
                if previous_bottom - 2 <= part.y + part.alto / 2 < item.y + 2 and part.y >= limit
            ]
            result.append(_finish(item, code, names, headers[column].cycle, True, []))
            previous_bottom = item.y + item.alto
    return result


def _extract_columns_without_headers(items: list[ItemTexto]) -> list[CursoExtraido]:
    codes = [(item, code) for item in items if (code := _normalize_code(item.texto)) is not None]
    if not codes:
        return []
    centers = sorted(item.x + item.ancho / 2 for item, _ in codes)
    widths = [item.ancho for item, _ in codes]
    gap = max(median(widths) * 1.5, 20)
    clusters: list[list[float]] = [[centers[0]]]
    for center in centers[1:]:
        if center - clusters[-1][-1] > gap:
            clusters.append([center])
        else:
            clusters[-1].append(center)

    if len(clusters) == 1:
        return []
    fake_headers = [
        _Header(cycle=index + 1, x=sum(cluster) / len(cluster), y=0, bottom=0)
        for index, cluster in enumerate(clusters)
    ]
    courses = _extract_columns(items, fake_headers)
    for course in courses:
        course.ciclo_detectado = False
        course.confiable = False
        course.nota = "; ".join(filter(None, [course.nota, "Ciclo asignado por posición; verifícalo"]))
    return courses


def _extract_sections(items: list[ItemTexto], default_cycle: int | None) -> list[CursoExtraido]:
    rows = agrupar_filas(items)
    result: list[CursoExtraido] = []
    current_cycle = default_cycle
    detected = True
    previous: CursoExtraido | None = None
    previous_row_bottom = 0.0
    for row in rows:
        row_text = " ".join(item.texto for item in row)
        header_cycle = cycle_from_text(row_text)
        if header_cycle is not None:
            current_cycle, detected, previous = header_cycle, True, None
            continue
        code_items = [(item, code) for item in row if (code := _normalize_code(item.texto)) is not None]
        row_top = min(item.y for item in row)
        row_height = median([item.alto for item in row]) or 12.0
        if code_items:
            item, code = code_items[0]
            name_items = [part for part in row if part is not item and _looks_like_name_part(part)]
            course = _finish(item, code, name_items, current_cycle, detected, [])
            if current_cycle is None:
                course.confiable = False
                course.nota = "; ".join(filter(None, [course.nota, "Sin ciclo detectado; indícalo"]))
            result.append(course)
            previous = course
        elif previous is not None and row_top - previous_row_bottom <= row_height * 1.6:
            extra = [part for part in row if _looks_like_name_part(part)]
            if extra:
                joined = f"{previous.name} {_join_name(extra)}".strip()
                previous.name = joined[:MAX_NAME_LENGTH]
                previous.linea = f"{previous.name} {previous.code}"
        previous_row_bottom = max(item.y + item.alto for item in row)
    return result


def _flag_duplicates(courses: list[CursoExtraido]) -> None:
    seen: dict[str, CursoExtraido] = {}
    for course in courses:
        first = seen.get(course.code)
        if first is None:
            seen[course.code] = course
            continue
        for target in (first, course):
            target.confiable = False
            if not target.nota or "repetido" not in target.nota:
                target.nota = "; ".join(filter(None, [target.nota, "Código repetido en el archivo"]))


def extraer_malla_documento(
    documento: DocumentoLeido, default_cycle: int | None = None
) -> list[CursoExtraido]:
    courses: list[CursoExtraido] = []
    for page in sorted({item.pagina for item in documento.items}):
        items = [item for item in documento.items if item.pagina == page]
        headers = _find_headers(items)
        if _is_column_layout(headers):
            courses.extend(_extract_columns(items, headers))
            continue
        if headers:
            courses.extend(_extract_sections(items, default_cycle))
            continue
        columns = _extract_columns_without_headers(items)
        courses.extend(columns or _extract_sections(items, default_cycle))
    _flag_duplicates(courses)
    courses.sort(key=lambda course: (course.pagina, course.cycle or 99))
    return courses
