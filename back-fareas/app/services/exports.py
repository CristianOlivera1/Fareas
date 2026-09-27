"""Reportes de asistencia — RF-16: Excel (openpyxl) y PDF (reportlab).

Funciones PURAS: reciben los datos ya consultados y devuelven los bytes del
archivo; los routers solo hacen la consulta y arman la respuesta HTTP con el
Content-Disposition. Sin dependencia del request ni de la sesión de BD.
"""
import io
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Encabezado institucional compartido por ambos formatos (RF-16)
TITULO = "FACULTAD DE INFORMÁTICA - UNAMBA"
SUBTITULO = "Reporte de Asistencia - Sistema Fareas"

AZUL = "155DFC"          # --fareas-primary
AZUL_CLARO = "E8F0FE"

# --- Columnas estándar (misma tabla en pantalla, Excel y PDF) ----------------
HEADERS = ["Estudiante", "Código", "Curso", "Grupo", "Aula", "Estado", "Fecha", "Hora", "Método"]
ANCHOS_PDF = [58 * mm, 18 * mm, 58 * mm, 12 * mm, 20 * mm, 22 * mm, 24 * mm, 16 * mm, 18 * mm]

COLORES_ESTADO = {
    "asistio": ("22C55E", "Asistió"),
    "tardanza": ("F59E0B", "Tardanza"),
    "falta": ("EF4444", "Falta"),
    "sin_registro": ("9CA3AF", "Sin registro"),
}


def _fila(r: dict) -> list[str]:
    hora = (r.get("marked_at") or "")[11:16] if r.get("marked_at") else "-"
    return [
        str(r.get("student_name", "")),
        str(r.get("student_code") or "-"),
        str(r.get("course_name", "")),
        str(r.get("group_code", "-")),
        str(r.get("room_code", "")),
        COLORES_ESTADO.get(str(r.get("status")), ("", str(r.get("status", "-"))))[1],
        str(r.get("att_date") or ""),
        hora,
        str(r.get("method", "")),
    ]


def _nombre_archivo(ext: str, desde: date | None, hasta: date | None, now: datetime) -> str:
    rango = f"_{desde.isoformat()}_{hasta.isoformat()}" if desde or hasta else ""
    return f"asistencia{rango}_{now:%Y%m%d_%H%M}.{ext}"


def nombre_excel(desde: date | None, hasta: date | None, now: datetime | None = None) -> str:
    return _nombre_archivo("xlsx", desde, hasta, now or datetime.now())


def nombre_pdf(desde: date | None, hasta: date | None, now: datetime | None = None) -> str:
    return _nombre_archivo("pdf", desde, hasta, now or datetime.now())


# ---------------------------------------------------------------------------
# Excel (openpyxl)
# ---------------------------------------------------------------------------
def excel_asistencia(filas: list[dict], titulo_periodo: str | None = None) -> bytes:
    """Libro de una hoja: encabezado institucional + tabla con estilos."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Asistencia"

    # Encabezado institucional
    ws.merge_cells("A1:I1")
    c = ws["A1"]
    c.value = TITULO
    c.font = Font(bold=True, size=13, color=AZUL)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells("A2:I2")
    c = ws["A2"]
    c.value = f"{SUBTITULO}{f' - {titulo_periodo}' if titulo_periodo else ''}"
    c.font = Font(bold=True, size=11, color="374151")
    c.alignment = Alignment(horizontal="center")
    ws.merge_cells("A3:I3")
    ws["A3"] = f"Generado: {datetime.now():%d/%m/%Y %H:%M}  ·  Registros: {len(filas)}"
    ws["A3"].font = Font(size=9, color="9CA3AF")
    ws["A3"].alignment = Alignment(horizontal="center")

    # Fila de encabezados
    fila_hdr = 5
    fill_hdr = PatternFill("solid", fgColor=AZUL)
    fino = Side(style="thin", color="D1D5DB")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    for col, titulo in enumerate(HEADERS, start=1):
        c = ws.cell(row=fila_hdr, column=col, value=titulo)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill_hdr
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = borde

    # Datos con color por estado
    fills_estado = {k: PatternFill("solid", fgColor=f"{v[0]}22") for k, v in COLORES_ESTADO.items()}
    for i, r in enumerate(filas):
        valores = _fila(r)
        for col, valor in enumerate(valores, start=1):
            c = ws.cell(row=fila_hdr + 1 + i, column=col, value=valor)
            c.border = borde
            if col == 6:  # Estado
                estado = str(r.get("status", ""))
                c.font = Font(bold=True, color=COLORES_ESTADO.get(estado, ("111827",))[0])
                fill = fills_estado.get(estado)
                if fill:
                    c.fill = fill

    # Anchos y freeze
    anchos = [32, 10, 38, 8, 12, 12, 12, 8, 10]
    for col, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(col)].width = ancho
    ws.freeze_panes = f"A{fila_hdr + 1}"
    ws.auto_filter.ref = f"A{fila_hdr}:I{fila_hdr + len(filas)}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF (reportlab)
# ---------------------------------------------------------------------------
def pdf_asistencia(filas: list[dict], titulo_periodo: str | None = None) -> bytes:
    """PDF horizontal con encabezado institucional y tabla paginada."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=14 * mm, bottomMargin=12 * mm, leftMargin=12 * mm, rightMargin=12 * mm,
        title=f"{TITULO} - {SUBTITULO}", author="Sistema Fareas",
    )
    styles = getSampleStyleSheet()
    st_titulo = ParagraphStyle("titulo", parent=styles["Title"], fontSize=13,
                               textColor=colors.HexColor(f"#{AZUL}"), spaceAfter=1 * mm)
    st_sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, alignment=1,
                            textColor=colors.HexColor("#374151"))
    st_pie = ParagraphStyle("pie", parent=styles["Normal"], fontSize=7.5,
                            alignment=1, textColor=colors.HexColor("#9CA3AF"))
    st_celda = ParagraphStyle("celda", parent=styles["Normal"], fontSize=7, leading=8.5)

    story: list = [
        Paragraph(TITULO, st_titulo),
        Paragraph(f"{SUBTITULO}{f' - {titulo_periodo}' if titulo_periodo else ''}", st_sub),
        Spacer(1, 1.5 * mm),
        Paragraph(f"Generado: {datetime.now():%d/%m/%Y %H:%M} · Registros: {len(filas)}", st_sub),
        Spacer(1, 3 * mm),
    ]

    hdr = [Paragraph(f"<b>{h}</b>", st_celda) for h in HEADERS]
    data = [hdr]
    for r in filas:
        fila = _fila(r)
        estado = str(r.get("status", ""))
        hexcolor = COLORES_ESTADO.get(estado, ("111827",))[0]
        fila[5] = f'<font color="#{hexcolor}"><b>{fila[5]}</b></font>'
        data.append([Paragraph(str(v), st_celda) for v in fila])

    tabla = Table(data, colWidths=ANCHOS_PDF, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{AZUL}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tabla)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("© Fareas · Facultad de Informática UNAMBA", st_pie))

    doc.build(story)
    return buf.getvalue()
