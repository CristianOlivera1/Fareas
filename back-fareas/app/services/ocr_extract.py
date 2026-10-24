from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
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
class CeldaRect:
    x: float
    y: float
    ancho: float
    alto: float
    pagina: int


@dataclass(slots=True)
class DocumentoLeido:
    tipo: str
    paginas: int
    items: list[ItemTexto]
    lineas: list[LineaTexto]
    celdas: list[CeldaRect] = field(default_factory=list)


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


def _normalizar_imagen(imagen: Image.Image) -> Image.Image:
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")
    if max(imagen.size) > MAX_LADO_PX:
        imagen.thumbnail((MAX_LADO_PX, MAX_LADO_PX), Image.Resampling.LANCZOS)
    return imagen


def detectar_celdas(imagen: Image.Image, pagina: int) -> list[CeldaRect]:
    import cv2

    gris = cv2.cvtColor(np.asarray(imagen), cv2.COLOR_RGB2GRAY)
    alto, ancho = gris.shape
    bordes = cv2.adaptiveThreshold(
        gris, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10
    )
    horizontales = cv2.morphologyEx(
        bordes,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(ancho // 25, 30), 1)),
    )
    verticales = cv2.morphologyEx(
        bordes,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(alto // 25, 30))),
    )
    rejilla = cv2.dilate(cv2.bitwise_or(horizontales, verticales), np.ones((3, 3), np.uint8))
    if cv2.countNonZero(rejilla) < (ancho + alto) * 2:
        return []

    total, _, estadisticas, _ = cv2.connectedComponentsWithStats(
        cv2.bitwise_not(rejilla), connectivity=4
    )
    celdas: list[CeldaRect] = []
    for indice in range(1, total):
        x, y, w, h, _ = (int(valor) for valor in estadisticas[indice])
        if w * h > ancho * alto * 0.6 or w < 20 or h < 12:
            continue
        celdas.append(CeldaRect(x=x, y=y, ancho=w, alto=h, pagina=pagina))
    return celdas


def _se_solapan(izquierda: ItemTexto, derecha: ItemTexto) -> bool:
    centro_x = izquierda.x + izquierda.ancho / 2
    centro_y = izquierda.y + izquierda.alto / 2
    otro_x = derecha.x + derecha.ancho / 2
    otro_y = derecha.y + derecha.alto / 2
    return (
        abs(centro_x - otro_x) < max(min(izquierda.ancho, derecha.ancho) * 0.5, 8)
        and abs(centro_y - otro_y) < max(min(izquierda.alto, derecha.alto) * 0.6, 6)
    )


def _reintentar_baja_confianza(
    imagen: Image.Image, items: list[ItemTexto], pagina: int
) -> list[ItemTexto]:
    dudosos = sorted(
        (
            item for item in items
            if item.confianza < 0.6 and len(item.texto.strip()) >= 4
        ),
        key=lambda item: item.confianza,
    )[:4]
    if not dudosos:
        return items

    resultado = list(items)
    for item in dudosos:
        izquierda = max(0, int(item.x) - 4)
        arriba = max(0, int(item.y) - int(item.alto) - 8)
        derecha = min(imagen.width, int(item.x + item.ancho) + 16)
        abajo = min(imagen.height, int(item.y + item.alto * 2) + 8)
        if derecha - izquierda < 20 or abajo - arriba < 10:
            continue

        recorte = imagen.crop((izquierda, arriba, derecha, abajo))
        nuevos = _items_de_ocr(np.asarray(recorte), pagina)
        if not nuevos:
            continue
        limite_derecho = item.x + item.ancho + 8
        otros = [existente for existente in resultado if existente is not item]
        reemplazos: list[ItemTexto] = []
        for nuevo in nuevos:
            nuevo.x += izquierda
            nuevo.y += arriba
            if nuevo.x + nuevo.ancho / 2 > limite_derecho:
                continue
            if any(_se_solapan(nuevo, existente) for existente in otros):
                continue
            reemplazos.append(nuevo)
        if not reemplazos:
            continue
        resultado = [existente for existente in resultado if existente is not item]
        resultado.extend(reemplazos)
    return sorted(resultado, key=lambda item: (item.pagina, item.y, item.x))


def _items_de_pdf_escaneado(raw: bytes) -> tuple[list[ItemTexto], int, list[CeldaRect]]:
    items: list[ItemTexto] = []
    celdas: list[CeldaRect] = []
    documento = pdfium.PdfDocument(raw)
    try:
        paginas = len(documento)
        if paginas > MAX_PAGINAS:
            raise ValueError(f"El documento supera el máximo de {MAX_PAGINAS} páginas")
        escala = DPI_OCR / 72
        for numero in range(paginas):
            pagina = documento[numero]
            imagen = _normalizar_imagen(pagina.render(scale=escala).to_pil())
            encontrados = _items_de_ocr(np.asarray(imagen), numero + 1)
            items.extend(_reintentar_baja_confianza(imagen, encontrados, numero + 1))
            celdas.extend(detectar_celdas(imagen, numero + 1))
    finally:
        documento.close()
    return items, paginas, celdas


def _items_de_imagen(raw: bytes) -> tuple[list[ItemTexto], list[CeldaRect]]:
    try:
        with Image.open(io.BytesIO(raw)) as imagen:
            normalizada = _normalizar_imagen(imagen)
            encontrados = _items_de_ocr(np.asarray(normalizada), 1)
            items = _reintentar_baja_confianza(normalizada, encontrados, 1)
            return items, detectar_celdas(normalizada, 1)
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
            items, paginas, celdas = _items_de_pdf_escaneado(raw)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("No se pudo interpretar el PDF escaneado") from exc
        return DocumentoLeido(
            tipo="pdf_ocr",
            paginas=paginas,
            items=items,
            lineas=agrupar_lineas(items),
            celdas=celdas,
        )

    if _es_imagen(raw):
        items, celdas = _items_de_imagen(raw)
        return DocumentoLeido(
            tipo="imagen",
            paginas=1,
            items=items,
            lineas=agrupar_lineas(items),
            celdas=celdas,
        )

    nombre = filename or "el archivo"
    raise ValueError(f"Formato no soportado en {nombre}; sube un PDF, JPG, PNG o WEBP")


_OCR_LOCK = asyncio.Semaphore(1)


async def leer_documento_async(
    raw: bytes, filename: str | None = None, forzar_ocr: bool = False
) -> DocumentoLeido:
    async with _OCR_LOCK:
        return await asyncio.to_thread(leer_documento, raw, filename, forzar_ocr)
