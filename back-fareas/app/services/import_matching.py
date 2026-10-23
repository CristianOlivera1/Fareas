from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.tables import AppUser, Course, Room

TITULOS = re.compile(r"\((?:dr|dra|mag|ing|lic)\.?\)", re.IGNORECASE)
NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")


@dataclass(slots=True)
class Coincidencia:
    valor: object
    puntaje: float
    motivo: str


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().upper()


def _compacto(texto: str | None) -> str:
    return NO_ALFANUMERICO.sub("", normalizar(texto))


def _similitud(izquierda: str, derecha: str) -> float:
    if not izquierda or not derecha:
        return 0.0
    if izquierda == derecha:
        return 1.0
    return SequenceMatcher(None, izquierda, derecha).ratio()


def _tokens_persona(texto: str | None) -> set[str]:
    limpio = TITULOS.sub(" ", normalizar(texto))
    return {token for token in NO_ALFANUMERICO.split(limpio) if len(token) > 1}


def _tokens_coinciden(izquierda: str, derecha: str) -> bool:
    if izquierda == derecha:
        return True
    if len(izquierda) >= 4 and len(derecha) >= 4:
        if izquierda in derecha or derecha in izquierda:
            return True
    return _similitud(izquierda, derecha) >= 0.85


def _similitud_persona(consulta: str | None, candidato: str | None) -> float:
    izquierda = _tokens_persona(consulta)
    derecha = _tokens_persona(candidato)
    if not izquierda or not derecha:
        return 0.0
    comunes = sum(
        1
        for token in izquierda
        if any(_tokens_coinciden(token, otro) for otro in derecha)
    )
    contencion = comunes / min(len(izquierda), len(derecha))
    jaccard = comunes / len(izquierda | derecha)
    orden = _similitud(" ".join(sorted(izquierda)), " ".join(sorted(derecha)))
    return max(contencion, jaccard, orden)


def _mejor(
    valores: Iterable[tuple[object, float, str]], minimo: float
) -> Coincidencia | None:
    ordenados = sorted(valores, key=lambda valor: valor[1], reverse=True)
    if not ordenados or ordenados[0][1] < minimo:
        return None
    if len(ordenados) > 1 and ordenados[0][1] - ordenados[1][1] < 0.03:
        return None
    valor, puntaje, motivo = ordenados[0]
    return Coincidencia(valor=valor, puntaje=round(puntaje, 4), motivo=motivo)


def sugerir_curso(
    codigo: str | None, nombre: str | None, cursos: Iterable[Course]
) -> Coincidencia | None:
    codigo_normal = _compacto(codigo)
    nombre_normal = normalizar(nombre)
    candidatos: list[tuple[object, float, str]] = []
    for curso in cursos:
        if codigo_normal and _compacto(curso.code) == codigo_normal:
            continue
        por_codigo = _similitud(codigo_normal, _compacto(curso.code))
        por_nombre = _similitud(nombre_normal, normalizar(curso.name))
        puntaje = max(por_codigo, por_nombre * 0.96)
        if puntaje < 0.70:
            continue
        motivo = "código parecido" if por_codigo >= por_nombre else "nombre parecido"
        candidatos.append((curso, puntaje, motivo))
    return _mejor(candidatos, 0.70)


def emparejar_docente(nombre: str | None, docentes: Iterable[AppUser]) -> Coincidencia | None:
    candidatos = [
        (docente, _similitud_persona(nombre, docente.full_name), "nombre parecido")
        for docente in docentes
    ]
    return _mejor(candidatos, 0.82)


def emparejar_aula(codigo: str | None, aulas: Iterable[Room]) -> Coincidencia | None:
    codigo_normal = _compacto(codigo)
    candidatos: list[tuple[object, float, str]] = []
    for aula in aulas:
        aula_normal = _compacto(aula.code)
        puntaje = _similitud(codigo_normal, aula_normal)
        if puntaje < 0.85:
            continue
        candidatos.append((aula, puntaje, "código de aula parecido"))
    return _mejor(candidatos, 0.85)
