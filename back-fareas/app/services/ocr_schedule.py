from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from statistics import median

import pdfplumber
from pydantic import BaseModel

from app.services.ocr_extract import MAX_PAGINAS, DocumentoLeido, ItemTexto, LineaTexto

DIAS: dict[str, int] = {
    "LUNES": 1, "LUN": 1, "LU": 1,
    "MARTES": 2, "MAR": 2,
    "MIÉRCOLES": 3, "MIERCOLES": 3, "MIÉ": 3, "MIE": 3,
    "JUEVES": 4, "JUE": 4,
    "VIERNES": 5, "VIE": 5,
    "SÁBADO": 6, "SABADO": 6, "SÁB": 6, "SAB": 6,
    "DOMINGO": 7, "DOM": 7,
}
_DIAS_ALT = "|".join(DIAS)

RE_BLOQUE = re.compile(
    r"(?<![A-ZÁÉÍÓÚ])([A-ZÁÉÍÓÚ]{3,10}(?:\s*/\s*[A-ZÁÉÍÓÚ]{3,10})*)\s+"
    r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})",
    re.IGNORECASE,
)
RE_CURSO = re.compile(r"\b([A-Z]{2,8}\d{2,4})\b")
RE_GRUPO = re.compile(r"(?:GRUPO|SECCIÓN|SECCION|SEC)\s*[:\-]?\s*([A-Z0-9]{1,3})\b", re.IGNORECASE)
RE_HORA_RANGO = re.compile(
    r"(?<!\d)(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})(?!\d)"
)
RE_AULA = re.compile(
    r"\b(?:LAB|L[A-ZÁÉÍÓÚ]?B|AULA|LABORATORIO)\s*[-:]?\s*([A-Z0-9][A-Z0-9-]{0,7})\b",
    re.IGNORECASE,
)
RE_DOCENTE = re.compile(
    r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{2,},\s*[A-Za-zÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑ\s.]{0,60})"
)

MAX_PESO_PDF = 10 * 1024 * 1024
CONFIANZA_MINIMA = 0.55


@dataclass(slots=True)
class _CabeceraDia:
    weekday: int
    centro: float
    y: float
    alto: float


@dataclass(slots=True)
class _EtiquetaHora:
    inicio: str
    fin: str
    y: float
    alto: float
    pagina: int


def _sin_tildes(texto: str) -> str:
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    ).upper()


_DIAS_NORMALIZADOS = {_sin_tildes(clave): valor for clave, valor in DIAS.items()}


class BloqueExtraido(BaseModel):
    course_code: str | None = None
    course_name: str | None = None
    group_code: str | None = None
    teacher_name: str | None = None
    room_code: str | None = None
    weekday: int
    start_time: str
    end_time: str
    confiable: bool = True
    nota: str | None = None
    linea: str = ""
    pagina: int = 1
    confianza: float = 1.0


def _hhmm(h: str, m: str) -> str:
    return f"{int(h):02d}:{m}"


def _limpiar_nombre(texto: str) -> str | None:
    texto = RE_BLOQUE.sub(" ", texto)
    texto = RE_GRUPO.sub(" ", texto)
    texto = re.split(r"\s{2,}", texto)[0]
    texto = texto.strip(" -–—:.,()")
    texto = re.sub(r"\s+", " ", texto)
    return texto[:160] or None


def _dia_de_cabecera(texto: str) -> int | None:
    limpio = re.sub(r"[^A-Z]", "", _sin_tildes(texto))
    return _DIAS_NORMALIZADOS.get(limpio)


def _rango_horario(match: re.Match[str]) -> tuple[str, str] | None:
    h1, m1, h2, m2 = match.groups()
    valido = (
        0 <= int(h1) < 24 and 0 <= int(m1) < 60
        and 0 <= int(h2) < 24 and 0 <= int(m2) < 60
        and (int(h1), int(m1)) < (int(h2), int(m2))
    )
    if not valido:
        return None
    return _hhmm(h1, m1), _hhmm(h2, m2)


def _cortar_docente(texto: str) -> str:
    return RE_DOCENTE.split(texto, maxsplit=1)[0]


def _limpiar_docente(texto: str | None) -> str | None:
    if not texto:
        return None
    limpio = re.sub(r"\((?:dr|dra|mag|ing|lic)\.?\)", " ", texto, flags=re.IGNORECASE)
    limpio = re.sub(r"\s+", " ", limpio).strip(" -–—:.,")
    return limpio[:160] or None


def _limpiar_aula(texto: str | None) -> str | None:
    if not texto:
        return None
    limpio = re.sub(r"\s+", " ", texto).strip(" -–—:.,()")
    return limpio[:20] or None


def _cabeceras_dias(items: list[ItemTexto]) -> list[_CabeceraDia]:
    candidatos: list[tuple[float, float, int, ItemTexto]] = []
    for item in items:
        weekday = _dia_de_cabecera(item.texto)
        if weekday is not None and weekday <= 5:
            candidatos.append((item.y, item.x + item.ancho / 2, weekday, item))
    if not candidatos:
        return []
    tope = min(candidato[0] for candidato in candidatos)
    alto = max(candidato[3].alto for candidato in candidatos)
    candidatos = [
        candidato for candidato in candidatos
        if candidato[0] <= tope + max(alto, 12) * 1.5
    ]
    por_dia: dict[int, _CabeceraDia] = {}
    for y, centro, weekday, item in sorted(candidatos, key=lambda c: (c[0], c[1])):
        if weekday not in por_dia:
            por_dia[weekday] = _CabeceraDia(weekday, centro, y, item.alto)
    return sorted(por_dia.values(), key=lambda cabecera: cabecera.centro)


def _columnas(headers: list[_CabeceraDia]) -> list[tuple[_CabeceraDia, float, float]]:
    if len(headers) < 2:
        return []
    centros = [header.centro for header in headers]
    limites = [centros[0] - (centros[1] - centros[0]) / 2]
    for izquierda, derecha in zip(centros, centros[1:], strict=False):
        limites.append((izquierda + derecha) / 2)
    limites.append(centros[-1] + (centros[-1] - centros[-2]) / 2)
    return [
        (header, limites[indice], limites[indice + 1])
        for indice, header in enumerate(headers)
    ]


def _etiquetas_hora(
    items: list[ItemTexto], lineas: list[LineaTexto], limite_izquierdo: float
) -> list[_EtiquetaHora]:
    etiquetas: list[_EtiquetaHora] = []
    for item in items:
        if item.x + item.ancho / 2 >= limite_izquierdo:
            continue
        match = RE_HORA_RANGO.search(item.texto)
        if match is None or match.start() > 2:
            continue
        rango = _rango_horario(match)
        if rango is None:
            continue
        etiquetas.append(
            _EtiquetaHora(rango[0], rango[1], item.y, item.alto, item.pagina)
        )
    if len(etiquetas) >= 2:
        return sorted(etiquetas, key=lambda etiqueta: etiqueta.y)

    for linea in lineas:
        if linea.x >= limite_izquierdo:
            continue
        match = RE_HORA_RANGO.search(linea.texto)
        if match is None or match.start() > 2:
            continue
        rango = _rango_horario(match)
        if rango is None:
            continue
        etiquetas.append(
            _EtiquetaHora(rango[0], rango[1], linea.y, linea.alto, linea.pagina)
        )
    return sorted(etiquetas, key=lambda etiqueta: etiqueta.y)


def _limites_filas(
    etiquetas: list[_EtiquetaHora], cabecera_inferior: float
) -> list[float]:
    alturas = [etiqueta.alto for etiqueta in etiquetas if etiqueta.alto > 0]
    alto = median(alturas) if alturas else 20.0
    primera = etiquetas[0]
    inicio = (
        cabecera_inferior
        if cabecera_inferior < primera.y
        else max(0.0, primera.y - max(alto * 1.5, 20.0))
    )
    limites = [inicio]
    for etiqueta in etiquetas[:-1]:
        limites.append(etiqueta.y + etiqueta.alto * 0.9)
    diferencias = [
        derecha.y - izquierda.y
        for izquierda, derecha in zip(etiquetas, etiquetas[1:], strict=False)
        if derecha.y > izquierda.y
    ]
    paso = median(diferencias) if diferencias else alto
    ultima = etiquetas[-1]
    limites.append(ultima.y + max(paso, ultima.alto) * 1.2)
    return limites


def _columna_de(
    item: ItemTexto, columnas: list[tuple[_CabeceraDia, float, float]]
) -> int | None:
    centro = item.x + item.ancho / 2
    for cabecera, izquierda, derecha in columnas:
        if izquierda <= centro < derecha:
            return cabecera.weekday
    return None


def _grupo_de_cabecera(items: list[ItemTexto], cabecera_inferior: float) -> str | None:
    for item in sorted(items, key=lambda item: item.y):
        if item.y >= cabecera_inferior:
            continue
        match = RE_GRUPO.search(item.texto.upper())
        if match:
            return match.group(1).upper()
    return None


def _bloque_de_celda(
    items: list[ItemTexto],
    *,
    weekday: int,
    etiqueta: _EtiquetaHora,
    grupo_cabecera: str | None,
) -> BloqueExtraido | None:
    ordenados = sorted(items, key=lambda item: (item.y, item.x))
    texto = re.sub(r"\s+", " ", " ".join(item.texto for item in ordenados)).strip()
    texto = texto.strip(" -–—:;,")
    match_curso = RE_CURSO.search(texto.upper())
    if match_curso is None:
        return None

    code = match_curso.group(1)
    resto = texto[match_curso.end():].strip()
    match_aula = RE_AULA.search(resto)
    match_docente = RE_DOCENTE.search(resto)
    cortes = [match.start() for match in (match_aula, match_docente) if match is not None]
    nombre_txt = resto[: min(cortes)] if cortes else _cortar_docente(resto)
    nombre = _limpiar_nombre(nombre_txt)
    teacher_name = _limpiar_docente(match_docente.group(1)) if match_docente else None
    room_code = _limpiar_aula(match_aula.group(0)) if match_aula else None
    match_grupo = RE_GRUPO.search(texto.upper())
    notas: list[str] = []
    confiable = True
    if match_grupo:
        grupo = match_grupo.group(1).upper()
    elif grupo_cabecera:
        grupo = grupo_cabecera
    else:
        grupo = "A"
        notas.append("Grupo no indicado en el horario; se asumió A")

    if not nombre:
        notas.append("Nombre del curso no detectado")
        confiable = False
    confianza = min(item.confianza for item in ordenados)
    if confianza < CONFIANZA_MINIMA:
        notas.append(f"baja confianza OCR ({confianza:.2f})")
        confiable = False

    return BloqueExtraido(
        course_code=code,
        course_name=nombre,
        group_code=grupo,
        teacher_name=teacher_name,
        room_code=room_code,
        weekday=weekday,
        start_time=etiqueta.inicio,
        end_time=etiqueta.fin,
        confiable=confiable,
        nota="; ".join(notas) or None,
        linea=texto[:200],
        pagina=etiqueta.pagina,
        confianza=round(confianza, 4),
    )


def _parsear_tabla(documento: DocumentoLeido) -> list[BloqueExtraido]:
    bloques: list[BloqueExtraido] = []
    vistos: set[tuple[str | None, str | None, int, str, str]] = set()

    for pagina in sorted({item.pagina for item in documento.items}):
        items = [item for item in documento.items if item.pagina == pagina]
        lineas = [linea for linea in documento.lineas if linea.pagina == pagina]
        headers = _cabeceras_dias(items)
        columnas = _columnas(headers)
        if not columnas:
            continue
        limite_izquierdo = columnas[0][1]
        etiquetas = _etiquetas_hora(items, lineas, limite_izquierdo)
        if len(etiquetas) < 2:
            continue
        cabecera_inferior = max(header.y + header.alto for header in headers)
        grupo_cabecera = _grupo_de_cabecera(items, cabecera_inferior)
        limites = _limites_filas(etiquetas, cabecera_inferior)

        for indice, etiqueta in enumerate(etiquetas):
            celdas: dict[int, list[ItemTexto]] = {}
            for item in items:
                centro_y = item.y + item.alto / 2
                if centro_y < limites[indice] or centro_y >= limites[indice + 1]:
                    continue
                weekday = _columna_de(item, columnas)
                if weekday is None:
                    continue
                celdas.setdefault(weekday, []).append(item)

            for weekday, items_celda in celdas.items():
                bloque = _bloque_de_celda(
                    items_celda,
                    weekday=weekday,
                    etiqueta=etiqueta,
                    grupo_cabecera=grupo_cabecera,
                )
                if bloque is None:
                    continue
                clave = (
                    bloque.course_code,
                    bloque.group_code,
                    bloque.weekday,
                    bloque.start_time,
                    bloque.end_time,
                )
                if clave in vistos:
                    continue
                vistos.add(clave)
                bloques.append(bloque)

    return sorted(
        bloques,
        key=lambda bloque: (
            bloque.weekday,
            bloque.start_time,
            bloque.course_code or "",
        ),
    )


def _lineas_de_pdf_texto(pdf_bytes: bytes) -> tuple[list[LineaTexto], int]:
    lineas: list[LineaTexto] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        paginas = len(pdf.pages)
        if paginas > MAX_PAGINAS:
            raise ValueError(f"El PDF supera el máximo de {MAX_PAGINAS} páginas")
        for numero, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text() or ""
            for indice, linea in enumerate(texto.splitlines()):
                if linea.strip():
                    lineas.append(
                        LineaTexto(
                            texto=linea.strip(),
                            x=0.0,
                            y=float(indice),
                            ancho=0.0,
                            alto=1.0,
                            confianza=1.0,
                            pagina=numero,
                        )
                    )
    return lineas, paginas


def _parsear_lineas(lineas: list[LineaTexto]) -> list[BloqueExtraido]:
    bloques: list[BloqueExtraido] = []
    curso_actual: tuple[str | None, str | None] = (None, None)
    grupo_actual: str | None = None

    for linea in lineas:
        texto = linea.texto.strip()
        if not texto:
            continue
        mayus = texto.upper()

        m_curso = RE_CURSO.search(mayus)
        if m_curso:
            code = m_curso.group(1)
            nombre = _limpiar_nombre(mayus[m_curso.end():])
            curso_actual = (code, nombre)

        m_grupo = RE_GRUPO.search(mayus)
        if m_grupo:
            grupo_actual = m_grupo.group(1).upper()

        for m in RE_BLOQUE.finditer(mayus):
            dias_txt, h1, m1, h2, m2 = m.groups()
            inicio, fin = _hhmm(h1, m1), _hhmm(h2, m2)
            valido = (
                0 <= int(h1) < 24 and 0 <= int(m1) < 60
                and 0 <= int(h2) < 24 and 0 <= int(m2) < 60
                and (int(h1), int(m1)) < (int(h2), int(m2))
            )
            code, nombre = curso_actual
            for dia in re.split(r"\s*/\s*", dias_txt.strip()):
                clave = re.sub(r"\s+", "", dia).upper()
                weekday = DIAS.get(clave)
                confiable = bool(valido and weekday is not None and code is not None and grupo_actual)
                nota = None
                if not valido:
                    nota = "horario ilegible o rango invertido"
                elif weekday is None:
                    nota = f"día no reconocido: {dia}"
                elif code is None:
                    nota = "línea de horario sin curso previo"
                elif not grupo_actual:
                    nota = "grupo/sección no detectado"
                elif weekday is not None and weekday > 5:
                    confiable = False
                    nota = "día fuera de la semana lectiva (Lun–Vie)"
                elif linea.confianza < CONFIANZA_MINIMA:
                    confiable = False
                    nota = f"baja confianza OCR ({linea.confianza:.2f})"
                bloques.append(
                    BloqueExtraido(
                        course_code=code,
                        course_name=nombre,
                        group_code=grupo_actual,
                        weekday=weekday or 0,
                        start_time=inicio,
                        end_time=fin,
                        confiable=confiable,
                        nota=nota,
                        linea=texto[:200],
                        pagina=linea.pagina,
                        confianza=round(linea.confianza, 4),
                    )
                )

    return bloques


def extraer_horarios(pdf_bytes: bytes) -> tuple[list[BloqueExtraido], int]:
    lineas, paginas = _lineas_de_pdf_texto(pdf_bytes)
    return _parsear_lineas(lineas), paginas


def extraer_horarios_documento(documento: DocumentoLeido) -> list[BloqueExtraido]:
    tabla = _parsear_tabla(documento)
    if tabla:
        return tabla
    return _parsear_lineas(documento.lineas)
