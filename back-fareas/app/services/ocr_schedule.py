"""OCR de horarios — RF-07: PDF de matrícula → propuesta editable.

``extraer_horarios(pdf_bytes)`` devuelve bloques horarios CANDIDATOS
(curso, grupo, día, horas) con una marca de confianza y la línea original
para que el admin corrija lo ambiguo ANTES de persistir (RF-07).

Alcance honesto (tesis): pdfplumber extrae TEXTO (la "constancia de
matrícula" es PDF digital, no escaneado). Un PDF de imagen pura devuelve
0 bloques y el endpoint lo reporta como no procesable — el OCR sobre
imagen NO es parte del alcance (PLAN §7).
"""
import io
import re

import pdfplumber
from pydantic import BaseModel

# 1=Lunes … 7=Domingo (mismo convenio de schedule_block.weekday)
DIAS: dict[str, int] = {
    "LUNES": 1, "LUN": 1, "LU": 1,
    "MARTES": 2, "MAR": 2,
    "MIÉRCOLES": 3, "MIERCOLES": 3, "MIÉ": 3, "MIE": 3,
    "JUEVES": 4, "JUE": 4,
    "VIERNES": 5, "VIE": 5,
    "SÁBADO": 6, "SABADO": 6, "SÁB": 6, "SAB": 6,
    "DOMINGO": 7, "DOM": 7,
}
_DIAS_ALT = "|".join(DIAS)  # el orden ya va de largo a corto

# 'LUN 08:00 - 10:00', 'MIÉ 14:00–16:00', 'LUN/MIE 08:00-10:00', 'MAR 8:00 a 10:00' no
# El token del día es genérico (3-4 letras): si no está en DIAS sale AMBIGUO
# (RF-07: los registros ambiguos se marcan para corrección manual).
RE_BLOQUE = re.compile(
    r"([A-ZÁÉÍÓÚ]{3,4}(?:\s*/\s*[A-ZÁÉÍÓÚ]{3,4})*)\s+(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})",
    re.IGNORECASE,
)
RE_CURSO = re.compile(r"\b([A-Z]{2,8}\d{2,4})\b")  # ISA903, TSTOCR901, SI504…
RE_GRUPO = re.compile(r"(?:GRUPO|SECCIÓN|SECCION|SEC)\s*[:\-]?\s*([A-Z0-9]{1,3})\b", re.IGNORECASE)

MAX_PESO_PDF = 10 * 1024 * 1024  # 10 MB es más que suficiente para una matrícula


class BloqueExtraido(BaseModel):
    course_code: str | None = None
    course_name: str | None = None
    group_code: str | None = None
    weekday: int
    start_time: str  # '08:00'
    end_time: str
    confiable: bool = True
    nota: str | None = None
    linea: str = ""


def _hhmm(h: str, m: str) -> str:
    return f"{int(h):02d}:{m}"


def _limpiar_nombre(texto: str) -> str | None:
    """Nombre de curso: texto tras el código, sin horario/grupo/puntuación suelta."""
    texto = RE_BLOQUE.sub(" ", texto)
    texto = RE_GRUPO.sub(" ", texto)
    texto = re.split(r"\s{2,}", texto)[0]  # columnas sueltas tras dobles espacios
    texto = texto.strip(" -–—:.,")
    texto = re.sub(r"\s+", " ", texto)
    return texto[:160] or None


def extraer_horarios(pdf_bytes: bytes) -> tuple[list[BloqueExtraido], int]:
    """Devuelve (bloques_extraidos, paginas_leidas).

    Estrategia de línea: un código de curso nuevo ('ISA903') establece el
    contexto; las líneas siguientes con 'DIA HH:MM - HH:MM' generan bloques
    de ese contexto. El grupo se toma de la misma línea del curso o de una
    línea 'Grupo X'. Todo lo dudoso sale con confiable=False y nota.
    """
    if len(pdf_bytes) > MAX_PESO_PDF:
        raise ValueError("El PDF supera el máximo de 10 MB")

    bloques: list[BloqueExtraido] = []
    paginas = 0
    curso_actual: tuple[str | None, str | None] = (None, None)  # (code, name)
    grupo_actual: str | None = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            paginas += 1
            texto = pagina.extract_text() or ""
            for linea in texto.splitlines():
                linea = linea.strip()
                if not linea:
                    continue
                mayus = linea.upper()

                # a) ¿Empieza aquí un curso nuevo?
                m_curso = RE_CURSO.search(mayus)
                if m_curso:
                    code = m_curso.group(1)
                    nombre = _limpiar_nombre(mayus[m_curso.end():])
                    curso_actual = (code, nombre)

                # b) ¿Grupo en esta línea?
                m_grupo = RE_GRUPO.search(mayus)
                if m_grupo:
                    grupo_actual = m_grupo.group(1).upper()

                # c) ¿Bloques horarios en esta línea?
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
                        bloques.append(BloqueExtraido(
                            course_code=code, course_name=nombre, group_code=grupo_actual,
                            weekday=weekday or 0, start_time=inicio, end_time=fin,
                            confiable=confiable, nota=nota, linea=linea[:200],
                        ))

    return bloques, paginas
