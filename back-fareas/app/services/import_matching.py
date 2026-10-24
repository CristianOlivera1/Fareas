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


RE_AULA = re.compile(r"^([A-Z]*?)([0-9OI]*[0-9][0-9OI]*)$")


def _partir_aula(codigo: str | None) -> tuple[str, str]:
    compacto = _compacto(codigo)
    encontrado = RE_AULA.match(compacto)
    if not encontrado:
        return compacto, ""
    numero = encontrado.group(2).replace("O", "0").replace("I", "1")
    return encontrado.group(1), numero


def emparejar_aula(codigo: str | None, aulas: Iterable[Room]) -> Coincidencia | None:
    prefijo, numero = _partir_aula(codigo)
    aulas = list(aulas)
    if numero:
        mismo_numero = [aula for aula in aulas if _partir_aula(aula.code)[1] == numero]
        if len(mismo_numero) == 1:
            igual = _partir_aula(mismo_numero[0].code)[0] == prefijo
            return Coincidencia(
                valor=mismo_numero[0],
                puntaje=1.0 if igual else 0.95,
                motivo="código de aula" if igual else "mismo número de aula",
            )
        if mismo_numero:
            candidatos = [
                (aula, _similitud(prefijo, _partir_aula(aula.code)[0]), "mismo número de aula")
                for aula in mismo_numero
            ]
            return _mejor(candidatos, 0.5)
    candidatos = [
        (aula, _similitud(_compacto(codigo), _compacto(aula.code)), "código de aula parecido")
        for aula in aulas
    ]
    return _mejor(candidatos, 0.85)
