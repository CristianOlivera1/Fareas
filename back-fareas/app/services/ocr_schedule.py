from __future__ import annotations

import io
import re

import pdfplumber
from pydantic import BaseModel

from app.services.ocr_extract import MAX_PAGINAS, DocumentoLeido, LineaTexto

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

MAX_PESO_PDF = 10 * 1024 * 1024
CONFIANZA_MINIMA = 0.55


class BloqueExtraido(BaseModel):
    course_code: str | None = None
    course_name: str | None = None
    group_code: str | None = None
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
    texto = texto.strip(" -–—:.,")
    texto = re.sub(r"\s+", " ", texto)
    return texto[:160] or None


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
    return _parsear_lineas(documento.lineas)
