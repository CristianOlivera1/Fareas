from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from functools import lru_cache
from statistics import median

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageOps

MAX_PESO_ARCHIVO = 10 * 1024 * 1024
MAX_PAGINAS = 10
MAX_LADO_PX = 2500
DPI_OCR = 220
PDF_MAGIC = b"%PDF-"
WEBP_MAGIC = b"RIFF"


@dataclass(slots=True)
class ItemTexto:
    texto: str
    x: float
    y: float
    ancho: float
    alto: float
    confianza: float
    pagina: int


@dataclass(slots=True)
class LineaTexto:
    texto: str
    x: float
    y: float
    ancho: float
    alto: float
    confianza: float
    pagina: int


@dataclass(slots=True)
class DocumentoLeido:
    tipo: str
    paginas: int
    items: list[ItemTexto]
    lineas: list[LineaTexto]


def _es_pdf(raw: bytes) -> bool:
    return raw.startswith(PDF_MAGIC)


def _es_imagen(raw: bytes) -> bool:
    return (
        raw.startswith(b"\xff\xd8\xff")
        or raw.startswith(b"\x89PNG\r\n\x1a\n")
        or (raw.startswith(WEBP_MAGIC) and raw[8:12] == b"WEBP")
    )


def _validar_tamano(raw: bytes) -> None:
    if not raw:
        raise ValueError("El archivo está vacío")
    if len(raw) > MAX_PESO_ARCHIVO:
        raise ValueError("El archivo supera el máximo de 10 MB")


def _items_de_pdf_texto(raw: bytes) -> tuple[list[ItemTexto], int]:
    items: list[ItemTexto] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        paginas = len(pdf.pages)
        if paginas > MAX_PAGINAS:
            raise ValueError(f"El documento supera el máximo de {MAX_PAGINAS} páginas")
        for numero, pagina in enumerate(pdf.pages, start=1):
            for word in pagina.extract_words():
                texto = (word.get("text") or "").strip()
                if not texto:
                    continue
                x0 = float(word.get("x0", 0))
                top = float(word.get("top", 0))
                x1 = float(word.get("x1", x0))
                bottom = float(word.get("bottom", top))
                items.append(
                    ItemTexto(
                        texto=texto,
                        x=x0,
                        y=top,
                        ancho=max(x1 - x0, 0),
                        alto=max(bottom - top, 0),
                        confianza=1.0,
                        pagina=numero,
                    )
                )
    return items, paginas


@lru_cache(maxsize=1)
def _motor_ocr():
    from rapidocr import RapidOCR

    return RapidOCR()


def _items_de_ocr(imagen: np.ndarray, pagina: int) -> list[ItemTexto]:
    resultado = _motor_ocr()(imagen, use_det=True, use_cls=True, use_rec=True)
    if resultado is None or not resultado.txts:
        return []
    cajas = resultado.boxes if resultado.boxes is not None else []
    scores = resultado.scores or []
    items: list[ItemTexto] = []
    for indice, texto in enumerate(resultado.txts):
        limpio = (texto or "").strip()
        if not limpio:
            continue
        caja = cajas[indice] if indice < len(cajas) else None
        if caja is None:
            xs = [0.0, 0.0, 0.0, 0.0]
            ys = [0.0, 0.0, 0.0, 0.0]
        else:
            xs = [float(punto[0]) for punto in caja]
            ys = [float(punto[1]) for punto in caja]
        confianza = float(scores[indice]) if indice < len(scores) else 0.0
        items.append(
            ItemTexto(
                texto=limpio,
                x=min(xs),
                y=min(ys),
                ancho=max(max(xs) - min(xs), 0),
                alto=max(max(ys) - min(ys), 0),
                confianza=confianza,
                pagina=pagina,
            )
        )
    return items


def _imagen_ocr(imagen: Image.Image) -> np.ndarray:
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")
    if max(imagen.size) > MAX_LADO_PX:
        imagen.thumbnail((MAX_LADO_PX, MAX_LADO_PX), Image.Resampling.LANCZOS)
    return np.asarray(imagen)


def _items_de_pdf_escaneado(raw: bytes) -> tuple[list[ItemTexto], int]:
    items: list[ItemTexto] = []
    documento = pdfium.PdfDocument(raw)
    try:
        paginas = len(documento)
        if paginas > MAX_PAGINAS:
            raise ValueError(f"El documento supera el máximo de {MAX_PAGINAS} páginas")
        escala = DPI_OCR / 72
        for numero in range(paginas):
            pagina = documento[numero]
            imagen = pagina.render(scale=escala).to_pil()
            items.extend(_items_de_ocr(_imagen_ocr(imagen), numero + 1))
    finally:
        documento.close()
    return items, paginas


def _items_de_imagen(raw: bytes) -> list[ItemTexto]:
    try:
        with Image.open(io.BytesIO(raw)) as imagen:
            return _items_de_ocr(_imagen_ocr(imagen), 1)
    except Image.UnidentifiedImageError as exc:
        raise ValueError("Formato no soportado; sube un PDF, JPG, PNG o WEBP") from exc


def agrupar_filas(items: list[ItemTexto]) -> list[list[ItemTexto]]:
    filas: list[list[ItemTexto]] = []
    for pagina in sorted({item.pagina for item in items}):
        de_pagina = [item for item in items if item.pagina == pagina]
        de_pagina.sort(key=lambda item: (item.y + item.alto / 2, item.x))
        alturas = [item.alto for item in de_pagina if item.alto > 0]
        tolerancia = max(6.0, (median(alturas) if alturas else 12.0) * 0.6)
        fila: list[ItemTexto] = []
        centro_fila: float | None = None

        for item in de_pagina:
            centro = item.y + item.alto / 2
            if centro_fila is None or abs(centro - centro_fila) <= tolerancia:
                fila.append(item)
                centro_fila = centro if centro_fila is None else centro_fila
            else:
                fila.sort(key=lambda item: item.x)
                filas.append(fila)
                fila = [item]
                centro_fila = centro
        if fila:
            fila.sort(key=lambda item: item.x)
            filas.append(fila)
    return filas


def agrupar_lineas(items: list[ItemTexto]) -> list[LineaTexto]:
    lineas: list[LineaTexto] = []
    for fila in agrupar_filas(items):
        x = min(item.x for item in fila)
        y = min(item.y for item in fila)
        ancho = max(item.x + item.ancho for item in fila) - x
        alto = max(item.y + item.alto for item in fila) - y
        lineas.append(
            LineaTexto(
                texto=" ".join(item.texto for item in fila),
                x=x,
                y=y,
                ancho=max(ancho, 0),
                alto=max(alto, 0),
                confianza=min(item.confianza for item in fila),
                pagina=fila[0].pagina,
            )
        )
    return lineas


def leer_documento(raw: bytes, filename: str | None = None, forzar_ocr: bool = False) -> DocumentoLeido:
    _validar_tamano(raw)

    if _es_pdf(raw):
        if not forzar_ocr:
            try:
                items, paginas = _items_de_pdf_texto(raw)
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError("No se pudo leer el PDF; ¿es un archivo válido?") from exc
            texto_util = sum(len(item.texto) for item in items)
            if len(items) >= 3 and texto_util >= 10:
                return DocumentoLeido(
                    tipo="pdf_texto", paginas=paginas, items=items, lineas=agrupar_lineas(items)
                )

        try:
            items, paginas = _items_de_pdf_escaneado(raw)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("No se pudo interpretar el PDF escaneado") from exc
        return DocumentoLeido(
            tipo="pdf_ocr", paginas=paginas, items=items, lineas=agrupar_lineas(items)
        )

    if _es_imagen(raw):
        items = _items_de_imagen(raw)
        return DocumentoLeido(tipo="imagen", paginas=1, items=items, lineas=agrupar_lineas(items))

    nombre = filename or "el archivo"
    raise ValueError(f"Formato no soportado en {nombre}; sube un PDF, JPG, PNG o WEBP")


_OCR_LOCK = asyncio.Semaphore(1)


async def leer_documento_async(
    raw: bytes, filename: str | None = None, forzar_ocr: bool = False
) -> DocumentoLeido:
    async with _OCR_LOCK:
        return await asyncio.to_thread(leer_documento, raw, filename, forzar_ocr)
