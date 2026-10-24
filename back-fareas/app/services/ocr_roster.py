from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from statistics import median

from pydantic import BaseModel, Field

from app.services.ocr_extract import DocumentoLeido, ItemTexto, agrupar_filas

MAX_FILAS = 200
CONFIANZA_MINIMA = 0.55
DOMINIO_POR_DEFECTO = "unamba.edu.pe"

RE_CODIGO = re.compile(r"(?<!\d)(\d{6})(?!\d)")
RE_DNI = re.compile(r"(?<!\d)(\d{8})(?!\d)")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_WHATSAPP = re.compile(r"(?<!\d)(?:\+?51[\s.-]?)?(9\d{2})[\s.-]?(\d{3})[\s.-]?(\d{3})(?!\d)")
RE_NO_NOMBRE = re.compile(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s,.'’-]")
RE_ROMANO_RUIDOSO = re.compile(r"([Ⅰ-Ⅻⅰ-ⅻ])[Il|1Ⅰ-ⅻ]*")
ROMANOS = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12,
}
NUMEROS_CJK = {
    "一": "I", "二": "II", "三": "III", "四": "IV", "五": "V",
    "六": "VI", "七": "VII", "八": "VIII", "九": "IX", "十": "X",
}
PALABRAS_DE_CICLO = ("CICLO", "SEMESTRE")
TIPOS_NOMBRE = ("full_name", "apellidos", "ap_pat", "ap_mat", "nombres")


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


@dataclass(slots=True)
class _Columna:
    tipo: str
    centro: float
    izquierda: float = float("-inf")
    derecha: float = float("inf")


def _sin_tildes(texto: str) -> str:
    return "".join(
        caracter for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    ).upper()


def _tipo_columna(texto: str) -> str | None:
    normal = _sin_tildes(texto)
    if "PATERNO" in normal:
        return "ap_pat"
    if "MATERNO" in normal:
        return "ap_mat"
    if any(clave in normal for clave in ("CORREO", "EMAIL", "MAIL")):
        return "email"
    if any(clave in normal for clave in ("WHATSAPP", "CELULAR", "TELEFONO", "TELF", "MOVIL")):
        return "whatsapp"
    if "CICLO" in normal or "SEMESTRE" in normal:
        return "semester"
    if "DNI" in normal or "DOCUMENTO" in normal:
        return "dni"
    if "CODIGO" in normal or "MATRICULA" in normal or re.search(r"\bCOD\b", normal):
        return "code"
    if ("APELLIDO" in normal and "NOMBRE" in normal) or any(
        clave in normal for clave in ("COMPLETO", "ALUMNO", "ESTUDIANTE")
    ):
        return "full_name"
    if "APELLIDO" in normal:
        return "apellidos"
    if "NOMBRE" in normal:
        return "nombres"
    if re.fullmatch(r"(?:N|NRO|NUM|ITEM|ORDEN|#)[\W°º.]*", normal.strip()):
        return "indice"
    return None


def _tipos_clave(texto: str) -> set[str]:
    tipos: set[str] = set()
    if "@" in texto:
        tipos.add("email")
    if RE_DNI.search(texto):
        tipos.add("dni")
    if RE_CODIGO.search(texto):
        tipos.add("code")
    return tipos


def _fusionar_cabeceras(
    items: list[ItemTexto], alto: float
) -> list[tuple[str, float]]:
    grupos: list[dict] = []
    for fila in agrupar_filas(items):
        en_linea: list[dict] = []
        for item in fila:
            if en_linea and item.x - en_linea[-1]["derecha"] <= alto:
                ultimo = en_linea[-1]
                ultimo["texto"] += f" {item.texto}"
                ultimo["derecha"] = max(ultimo["derecha"], item.x + item.ancho)
                ultimo["abajo"] = max(ultimo["abajo"], item.y + item.alto)
            else:
                en_linea.append(
                    {
                        "texto": item.texto,
                        "izquierda": item.x,
                        "derecha": item.x + item.ancho,
                        "arriba": item.y,
                        "abajo": item.y + item.alto,
                    }
                )
        for nuevo in en_linea:
            destino = None
            for grupo in grupos:
                solape = min(grupo["derecha"], nuevo["derecha"]) - max(
                    grupo["izquierda"], nuevo["izquierda"]
                )
                menor = min(
                    grupo["derecha"] - grupo["izquierda"], nuevo["derecha"] - nuevo["izquierda"]
                )
                if solape > 0.3 * max(menor, 1.0) and 0 <= nuevo["arriba"] - grupo["abajo"] <= alto:
                    destino = grupo
                    break
            if destino is None:
                grupos.append(nuevo)
            else:
                destino["texto"] += f" {nuevo['texto']}"
                destino["izquierda"] = min(destino["izquierda"], nuevo["izquierda"])
                destino["derecha"] = max(destino["derecha"], nuevo["derecha"])
                destino["abajo"] = nuevo["abajo"]
    return [(g["texto"], (g["izquierda"] + g["derecha"]) / 2) for g in grupos]


def _columnas_de_cabecera(items: list[ItemTexto], alto: float) -> list[_Columna]:
    columnas: list[_Columna] = []
    vistos: set[str] = set()
    for texto, centro in sorted(_fusionar_cabeceras(items, alto), key=lambda g: g[1]):
        tipo = _tipo_columna(texto)
        if tipo is None or tipo in vistos:
            continue
        vistos.add(tipo)
        columnas.append(_Columna(tipo=tipo, centro=centro))
    if len(vistos & {"code", "dni", "email"}) < 2:
        return []
    for indice, columna in enumerate(columnas[:-1]):
        corte = (columna.centro + columnas[indice + 1].centro) / 2
        columna.derecha = corte
        columnas[indice + 1].izquierda = corte
    return columnas


def _columna_de(item: ItemTexto, columnas: list[_Columna]) -> str | None:
    mejor: tuple[float, str] | None = None
    for columna in columnas:
        solape = min(item.x + item.ancho, columna.derecha) - max(item.x, columna.izquierda)
        if solape > 0 and (mejor is None or solape > mejor[0]):
            mejor = (solape, columna.tipo)
    return mejor[1] if mejor else None


def _bandas(items: list[ItemTexto], umbral: float) -> list[list[ItemTexto]]:
    bandas: list[list[ItemTexto]] = []
    fondo = float("-inf")
    for item in sorted(items, key=lambda i: (i.y, i.x)):
        if bandas and item.y <= fondo + umbral:
            bandas[-1].append(item)
        else:
            bandas.append([item])
            fondo = float("-inf")
        fondo = max(fondo, item.y + item.alto)
    return bandas


def _filas_de_banda(banda: list[ItemTexto], alto: float) -> list[list[ItemTexto]]:
    claves = sorted(
        (item for item in banda if _tipos_clave(item.texto)),
        key=lambda i: i.y + i.alto / 2,
    )
    if not claves:
        return []
    grupos: list[list[ItemTexto]] = []
    for item in claves:
        centro = item.y + item.alto / 2
        ultimo = grupos[-1] if grupos else None
        if ultimo and abs(
            centro - sum(i.y + i.alto / 2 for i in ultimo) / len(ultimo)
        ) <= max(6.0, alto * 0.6):
            ultimo.append(item)
        else:
            grupos.append([item])

    filas: list[list[ItemTexto]] = []
    tipos_fila: set[str] = set()
    for grupo in grupos:
        tipos: set[str] = set()
        for item in grupo:
            tipos |= _tipos_clave(item.texto)
        if filas and not (tipos & tipos_fila):
            filas[-1].extend(grupo)
            tipos_fila |= tipos
        else:
            filas.append(list(grupo))
            tipos_fila = set(tipos)
    if len(filas) == 1:
        return [list(banda)]

    tramos = [
        (min(i.y for i in fila), max(i.y + i.alto for i in fila)) for fila in filas
    ]

    def distancia(indice: int, centro: float) -> float:
        arriba, abajo = tramos[indice]
        if arriba <= centro <= abajo:
            return 0.0
        return min(abs(centro - arriba), abs(centro - abajo))

    resultado: list[list[ItemTexto]] = [[] for _ in filas]
    for item in banda:
        centro = item.y + item.alto / 2
        cercano = min(range(len(filas)), key=lambda n: distancia(n, centro))
        resultado[cercano].append(item)
    return resultado


def _normalizar_ciclo(texto: str) -> int | None:
    limpio = RE_ROMANO_RUIDOSO.sub(r"\1", texto.strip())
    limpio = unicodedata.normalize("NFKC", limpio)
    for cjk, romano in NUMEROS_CJK.items():
        limpio = limpio.replace(cjk, romano)
    limpio = re.sub(r"(?i)\b(?:ciclo|semestre)\b", " ", limpio)
    limpio = re.sub(r"(?i)(?<=\d)(?:do|to|er|ro|vo|mo|no|°|º|ª)\b", "", limpio)
    limpio = re.sub(r"[^A-Za-z0-9|!]", "", limpio)
    if not limpio:
        return None
    if re.fullmatch(r"[IVXlL|!]+", limpio) and re.search(r"[IVXl|!]", limpio):
        limpio = limpio.replace("l", "I").replace("|", "I").replace("!", "I")
    limpio = limpio.upper()
    if limpio in ROMANOS:
        return ROMANOS[limpio]
    if re.fullmatch(r"\d{1,2}", limpio) and 1 <= int(limpio) <= 12:
        return int(limpio)
    return None


def _ciclo_de_tokens(tokens: list[str]) -> tuple[int | None, str | None]:
    for token in reversed(tokens):
        if token.endswith("."):
            continue
        ciclo = _normalizar_ciclo(token)
        if ciclo is not None:
            return ciclo, token
    return None, None


def _limpiar_nombre(texto: str) -> str:
    texto = RE_EMAIL.sub(" ", texto)
    texto = RE_NO_NOMBRE.sub(" ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" -–—:;,.")
    texto = re.sub(r"\s+,", ",", texto)
    return re.sub(r",(?=\S)", ", ", texto)


def _normalizar_whatsapp(texto: str) -> str | None:
    match = RE_WHATSAPP.search(texto)
    return "".join(match.groups()) if match else None


def _correo_de(items: list[ItemTexto]) -> str | None:
    ordenados = sorted(items, key=lambda i: (i.y, i.x))
    for indice, item in enumerate(ordenados):
        if "@" not in item.texto:
            continue
        directo = RE_EMAIL.search(item.texto)
        if directo:
            return directo.group(0)
        candidato = item.texto.replace(" ", "")
        siguiente = indice + 1
        while siguiente < len(ordenados) and siguiente <= indice + 2:
            coincide = RE_EMAIL.search(candidato)
            if coincide and not candidato.endswith(("@", ".")):
                return coincide.group(0)
            candidato += ordenados[siguiente].texto.replace(" ", "")
            siguiente += 1
        coincide = RE_EMAIL.search(candidato)
        if coincide:
            return coincide.group(0)
    return None


def _texto_de(items: list[ItemTexto]) -> str:
    return " ".join(item.texto for linea in agrupar_filas(items) for item in linea)


def _texto_columna(items: list[ItemTexto], columnas: list[_Columna], tipo: str) -> str:
    return _texto_de([i for i in items if _columna_de(i, columnas) == tipo])


def _nombre_de_columnas(items: list[ItemTexto], columnas: list[_Columna]) -> str:
    partes = {
        tipo: _limpiar_nombre(_texto_columna(items, columnas, tipo)) for tipo in TIPOS_NOMBRE
    }
    if partes["full_name"]:
        return partes["full_name"]
    apellidos = " ".join(
        parte for parte in (partes["ap_pat"], partes["ap_mat"], partes["apellidos"]) if parte
    )
    if apellidos and partes["nombres"]:
        return f"{apellidos}, {partes['nombres']}"
    return apellidos or partes["nombres"]


def _numero_de(
    patron: re.Pattern[str],
    texto: str,
    de_columna: str,
    largo: int,
) -> str | None:
    compacto = re.sub(r"\s", "", de_columna)
    if re.fullmatch(rf"\d{{{largo}}}", compacto):
        return compacto
    coincide = patron.search(texto)
    return coincide.group(1) if coincide else None


def _es_resto_de_correo(token: str, correo: str | None) -> bool:
    if not correo or len(token) < 5 or not ("." in token or "@" in token):
        return False
    return token.lower().strip(".") in correo.lower()


def _alumno_de_fila(
    items: list[ItemTexto], columnas: list[_Columna], numero: int
) -> AlumnoExtraido | None:
    ordenados = [i for linea in agrupar_filas(items) for i in linea]
    linea = " ".join(i.texto for i in ordenados)

    correo = _correo_de(items)
    sin_correo = linea.replace(correo, " ") if correo else linea

    codigo = _numero_de(RE_CODIGO, sin_correo, _texto_columna(items, columnas, "code"), 6)
    dni = _numero_de(RE_DNI, sin_correo, _texto_columna(items, columnas, "dni"), 8)
    restante = sin_correo
    for valor in (codigo, dni):
        if valor:
            restante = restante.replace(valor, " ", 1)

    whatsapp = _normalizar_whatsapp(_texto_columna(items, columnas, "whatsapp"))
    if whatsapp is None:
        whatsapp = _normalizar_whatsapp(restante)
    if whatsapp:
        restante = RE_WHATSAPP.sub(" ", restante, count=1)

    if not (codigo or dni or correo):
        return None

    con_columna_nombre = any(c.tipo in TIPOS_NOMBRE for c in columnas)
    ciclo, token_ciclo = None, None
    if any(c.tipo == "semester" for c in columnas):
        ciclo, _ = _ciclo_de_tokens(_texto_columna(items, columnas, "semester").split())

    if con_columna_nombre:
        ajenos = [i for i in items if _columna_de(i, columnas) not in TIPOS_NOMBRE]
        base = RE_EMAIL.sub(" ", _texto_de(ajenos))
    else:
        base = restante
    tokens = [
        t for t in base.split()
        if not re.fullmatch(r"[\d+().-]+", t)
        and t not in (codigo, dni)
        and not _es_resto_de_correo(t, correo)
        and _sin_tildes(t).strip(":.") not in PALABRAS_DE_CICLO
    ]

    if ciclo is None:
        ciclo, token_ciclo = _ciclo_de_tokens(tokens)

    if con_columna_nombre:
        nombre = _nombre_de_columnas(items, columnas)
    else:
        if token_ciclo in tokens:
            tokens.remove(token_ciclo)
        nombre = _limpiar_nombre(" ".join(tokens))

    alumno = AlumnoExtraido(
        fila=numero,
        code=codigo,
        dni=dni,
        full_name=nombre or None,
        email=correo,
        semester=ciclo,
        whatsapp=whatsapp,
        linea=linea[:200],
        pagina=ordenados[0].pagina,
    )
    if min(i.confianza for i in items) < CONFIANZA_MINIMA:
        alumno.confiable = False
        alumno.nota = "baja confianza OCR"
    return alumno


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
    alumnos: list[AlumnoExtraido] = []
    vistos_codigo: set[str] = set()
    vistos_dni: set[str] = set()
    vistos_email: set[str] = set()
    columnas: list[_Columna] = []

    for pagina in sorted({item.pagina for item in documento.items}):
        items = [i for i in documento.items if i.pagina == pagina and i.texto.strip()]
        alturas = [i.alto for i in items if i.alto > 0]
        alto = median(alturas) if alturas else 14.0
        claves = [i for i in items if _tipos_clave(i.texto)]
        if not claves:
            continue
        tope = min(i.y for i in claves)
        cabecera = [
            i for i in items
            if i.y + i.alto <= tope + 2
            and tope - (i.y + i.alto) <= alto * 6
            and _tipo_columna(i.texto) is not None
        ]
        encontradas = _columnas_de_cabecera(cabecera, alto) if cabecera else []
        if encontradas:
            columnas = encontradas
        ids_cabecera = {id(i) for i in cabecera}
        datos = [i for i in items if id(i) not in ids_cabecera]

        for banda in _bandas(datos, max(alto * 0.9, 6.0)):
            for fila in _filas_de_banda(banda, alto):
                alumno = _alumno_de_fila(fila, columnas, len(alumnos) + 1)
                if alumno is None:
                    continue
                if alumno.semester is None:
                    alumno.nota = alumno.nota or "Ciclo no detectado; se usó el ciclo por defecto"
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
