from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from app.services.ocr_extract import DocumentoLeido, ItemTexto, agrupar_filas

MAX_FILAS = 200
CONFIANZA_MINIMA = 0.55
DOMINIO_POR_DEFECTO = "unamba.edu.pe"

RE_CODIGO = re.compile(r"(?<!\d)(\d{6})(?!\d)")
RE_DNI = re.compile(r"(?<!\d)(\d{8})(?!\d)")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ROMANOS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}
CABECERAS = ("CODIGO", "MATRICULA", "DNI", "APELLIDO", "NOMBRE", "ALUMNO", "CORREO", "EMAIL", "CICLO")


class AlumnoExtraido(BaseModel):
    fila: int
    code: str | None = None
    dni: str | None = None
    full_name: str | None = None
    email: str | None = None
    email_generado: bool = False
    semester: int | None = None
    whatsapp: str | None = None
    confiable: bool = True
    duplicado: bool = False
    errores: list[str] = Field(default_factory=list)
    nota: str | None = None
    linea: str = ""
    pagina: int = 1


def _sin_tildes(texto: str) -> str:
    return "".join(
        caracter for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    ).upper()


def _texto(fila: list[ItemTexto]) -> str:
    return " ".join(item.texto for item in fila).strip()


def _rangos_de_columnas(filas: list[list[ItemTexto]]) -> dict[str, tuple[float, float]]:
    for fila in filas[:15]:
        normal = _sin_tildes(_texto(fila))
        if not any(clave in normal for clave in CABECERAS):
            continue
        anclas: dict[str, ItemTexto] = {}
        for item in fila:
            texto = _sin_tildes(item.texto)
            if "CODIGO" in texto or "MATRICULA" in texto:
                anclas.setdefault("code", item)
            elif "DNI" in texto:
                anclas.setdefault("dni", item)
            elif "CORREO" in texto or "EMAIL" in texto:
                anclas.setdefault("email", item)
            elif "CICLO" in texto or "SEMESTRE" in texto:
                anclas.setdefault("semester", item)
            elif "APELLIDO" in texto or "NOMBRE" in texto or "ALUMNO" in texto:
                anclas.setdefault("full_name", item)
        if "code" not in anclas and "dni" not in anclas:
            continue
        ordenadas = sorted(anclas.items(), key=lambda par: par[1].x)
        limites: dict[str, tuple[float, float]] = {}
        for indice, (campo, item) in enumerate(ordenadas):
            fin = ordenadas[indice + 1][1].x - 4 if indice + 1 < len(ordenadas) else 10_000.0
            limites[campo] = (item.x - 4, max(fin, item.x + item.ancho))
        return limites
    return {}


def _campos_por_columnas(
    fila: list[ItemTexto], rangos: dict[str, tuple[float, float]]
) -> dict[str, str]:
    campos: dict[str, list[str]] = {campo: [] for campo in rangos}
    for item in fila:
        centro = item.x + item.ancho / 2
        for campo, (inicio, fin) in rangos.items():
            if inicio <= centro <= fin:
                campos[campo].append(item.texto)
                break
    return {campo: " ".join(partes).strip() for campo, partes in campos.items()}


def _limpiar_nombre(texto: str) -> str:
    texto = RE_CODIGO.sub(" ", texto)
    texto = RE_DNI.sub(" ", texto)
    texto = RE_EMAIL.sub(" ", texto)
    texto = re.sub(r"^\s*\d{1,3}\s+", "", texto)
    texto = re.sub(r"\b(?:N°|NRO|NRO\.|ITEM)\b", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip(" -–—:;,.")


def _semestre_de_texto(texto: str) -> int | None:
    limpio = texto.strip().upper()
    if not limpio:
        return None
    if limpio in ROMANOS:
        return ROMANOS[limpio]
    match = re.search(r"(?<!\d)(1[0-2]|[1-9])(?!\d)", limpio)
    return int(match.group(1)) if match else None


def _es_cabecera(linea: str) -> bool:
    normal = _sin_tildes(linea)
    if "CODIGO" in normal and ("DNI" in normal or "APELLIDO" in normal or "NOMBRE" in normal):
        return True
    return normal.startswith(("TOTAL", "PAGINA", "PÁGINA"))


def validar_alumno(
    alumno: AlumnoExtraido,
    *,
    default_semester: int | None,
    dominio: str,
    vistos_codigo: set[str],
    vistos_dni: set[str],
    vistos_email: set[str],
) -> None:
    if alumno.code:
        alumno.code = re.sub(r"\D", "", alumno.code)
    if not alumno.code or len(alumno.code) != 6:
        alumno.errores.append("Falta el código de matrícula de 6 dígitos")

    if alumno.dni:
        alumno.dni = re.sub(r"\D", "", alumno.dni)
    if not alumno.dni or len(alumno.dni) != 8:
        alumno.errores.append("Falta el DNI de 8 dígitos")

    if alumno.full_name:
        alumno.full_name = re.sub(r"\s+", " ", alumno.full_name).strip()
    if not alumno.full_name or len(alumno.full_name) < 3:
        alumno.errores.append("Falta el nombre del alumno")
    elif len(alumno.full_name) > 160:
        alumno.full_name = alumno.full_name[:160]

    if not alumno.email and alumno.code and len(alumno.code) == 6:
        alumno.email = f"{alumno.code}@{dominio}"
        alumno.email_generado = True
    if alumno.email:
        alumno.email = alumno.email.strip().lower()
    if not alumno.email or not RE_EMAIL.fullmatch(alumno.email):
        alumno.errores.append("El correo no es válido")

    if alumno.semester is None:
        alumno.semester = default_semester
    if alumno.semester is None:
        alumno.errores.append("Falta el ciclo del alumno")
    elif alumno.semester < 1 or alumno.semester > 12:
        alumno.errores.append("El ciclo debe estar entre 1 y 12")

    if alumno.code and alumno.code in vistos_codigo:
        alumno.errores.append(f"El código {alumno.code} está repetido en el archivo")
        alumno.duplicado = True
    if alumno.dni and alumno.dni in vistos_dni:
        alumno.errores.append(f"El DNI {alumno.dni} está repetido en el archivo")
    if alumno.email and alumno.email in vistos_email:
        alumno.errores.append(f"El correo {alumno.email} está repetido en el archivo")
    if alumno.code:
        vistos_codigo.add(alumno.code)
    if alumno.dni:
        vistos_dni.add(alumno.dni)
    if alumno.email:
        vistos_email.add(alumno.email)

    alumno.confiable = alumno.confiable and not alumno.errores


def parsear_nomina(
    documento: DocumentoLeido,
    *,
    default_semester: int,
    dominio_email: str = DOMINIO_POR_DEFECTO,
) -> list[AlumnoExtraido]:
    filas = agrupar_filas(documento.items)
    rangos = _rangos_de_columnas(filas)
    alumnos: list[AlumnoExtraido] = []
    vistos_codigo: set[str] = set()
    vistos_dni: set[str] = set()
    vistos_email: set[str] = set()

    for fila in filas:
        linea = _texto(fila)
        if not linea or _es_cabecera(linea):
            continue
        por_columna = _campos_por_columnas(fila, rangos)

        code = RE_CODIGO.search(linea)
        dni = RE_DNI.search(linea)
        email = RE_EMAIL.search(linea)
        code_txt = (por_columna.get("code") or "").strip()
        if not re.fullmatch(r"\d{6}", code_txt):
            code_txt = code.group(1) if code else ""
        dni_txt = (por_columna.get("dni") or "").strip()
        if not re.fullmatch(r"\d{8}", dni_txt):
            dni_txt = dni.group(1) if dni else ""
        email_txt = (por_columna.get("email") or "").strip()
        if not RE_EMAIL.fullmatch(email_txt):
            email_txt = email.group(0) if email else ""

        nombre_col = por_columna.get("full_name", "")
        nombre = _limpiar_nombre(nombre_col) if nombre_col else ""
        if not nombre:
            nombre = _limpiar_nombre(linea)

        if not code_txt and not dni_txt and not email_txt:
            continue
        if not any(caracter.isalpha() for caracter in linea):
            continue

        alumno = AlumnoExtraido(
            fila=len(alumnos) + 1,
            code=code_txt or None,
            dni=dni_txt or None,
            full_name=nombre or None,
            email=email_txt or None,
            semester=_semestre_de_texto(por_columna.get("semester", "")),
            linea=linea[:200],
            pagina=fila[0].pagina,
        )
        alumno.nota = None
        if min((item.confianza for item in fila), default=1.0) < CONFIANZA_MINIMA:
            alumno.confiable = False
            alumno.nota = "baja confianza OCR"
        validar_alumno(
            alumno,
            default_semester=default_semester,
            dominio=dominio_email,
            vistos_codigo=vistos_codigo,
            vistos_dni=vistos_dni,
            vistos_email=vistos_email,
        )
        alumnos.append(alumno)
        if len(alumnos) > MAX_FILAS:
            raise ValueError(f"La nómina supera el máximo de {MAX_FILAS} filas")

    return alumnos
