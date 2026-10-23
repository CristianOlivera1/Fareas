from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import delete, select

from app.services.ocr_extract import DocumentoLeido, ItemTexto, agrupar_lineas
from app.services.ocr_roster import parsear_nomina
from app.tables import AppUser, AuditLog, Enrollment
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"
CODIGOS = ("997101", "997102", "997103", "997104")
DNIS = ("75551001", "75551002", "75551003", "75551004")
NOMBRES = (
    "QUISPE MAMANI, RAUL",
    "FLORES CANO, MARIA",
    "HUAMAN SOTO, LUIS",
    "SOTO VARGAS, ANA",
)


def _fuente(tamano: int):
    for ruta in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def _imagen_nomina() -> bytes:
    imagen = Image.new("RGB", (1800, 700), "white")
    dibujo = ImageDraw.Draw(imagen)
    fuente = _fuente(28)
    columnas = [
        ("N°", 40),
        ("CODIGO", 140),
        ("DNI", 360),
        ("APELLIDOS Y NOMBRES", 620),
        ("CORREO", 1280),
        ("CICLO", 1650),
    ]
    for texto, x in columnas:
        dibujo.text((x, 40), texto, fill="black", font=fuente)
    filas = [
        ("1", CODIGOS[0], DNIS[0], NOMBRES[0], f"{CODIGOS[0]}@unamba.edu.pe", "2"),
        ("2", CODIGOS[1], DNIS[1], NOMBRES[1], "", "2"),
        ("3", CODIGOS[2], DNIS[2], NOMBRES[2], f"{CODIGOS[2]}@unamba.edu.pe", "2"),
    ]
    y = 110
    for fila in filas:
        for (_texto, x), valor in zip(columnas, fila, strict=True):
            dibujo.text((x, y), valor, fill="black", font=fuente)
        y += 60
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


async def _limpiar_usuarios(db) -> None:
    usuarios = (
        await db.exec(select(AppUser).where(AppUser.code.in_(CODIGOS)))
    ).all()
    ids = [usuario.id for usuario in usuarios]
    if ids:
        await db.exec(delete(Enrollment).where(Enrollment.student_id.in_(ids)))
        await db.exec(
            delete(AuditLog).where(
                AuditLog.entity == "app_user", AuditLog.entity_id.in_(ids)
            )
        )
        for usuario in usuarios:
            await db.delete(usuario)
    await db.commit()


@pytest.fixture
async def escenario(db_session):
    await _limpiar_usuarios(db_session)
    await limpiar(db_session)
    datos = await crear(db_session)
    yield datos
    await _limpiar_usuarios(db_session)
    await limpiar(db_session)


def _subir(client, headers, contenido: bytes | None = None, nombre: str = "nomina.png"):
    return client.post(
        f"{API}/students/import-preview",
        headers=headers,
        data={"default_semester": "2"},
        files={"file": (nombre, BytesIO(contenido or _imagen_nomina()), "image/png")},
    )


def _item(texto: str, x: float, y: float, ancho: float = 120) -> ItemTexto:
    return ItemTexto(
        texto=texto, x=x, y=y, ancho=ancho, alto=20, confianza=0.99, pagina=1
    )


def test_parser_nomina_por_columnas():
    items = [
        _item("CODIGO", 140, 10, 90), _item("DNI", 360, 10, 50),
        _item("APELLIDOS Y NOMBRES", 620, 10, 250), _item("CORREO", 1280, 10, 90),
        _item("CICLO", 1650, 10, 60),
        _item("997101", 140, 60), _item("75551001", 360, 60),
        _item("QUISPE MAMANI, RAUL", 620, 60, 300), _item("2", 1650, 60, 20),
        _item("997102", 140, 120), _item("75551002", 360, 120),
        _item("FLORES CANO, MARIA", 620, 120, 300),
        _item("997101", 140, 180), _item("75551003", 360, 180),
        _item("SOTO VARGAS, ANA", 620, 180, 300),
    ]
    documento = DocumentoLeido(
        tipo="imagen", paginas=1, items=items, lineas=agrupar_lineas(items)
    )
    alumnos = parsear_nomina(documento, default_semester=3)
    assert len(alumnos) == 3
    assert alumnos[0].code == "997101" and alumnos[0].semester == 2
    assert alumnos[0].email == "997101@unamba.edu.pe"
    assert alumnos[1].email_generado is True
    assert alumnos[2].duplicado is True
    assert "repetido" in alumnos[2].errores[0]


async def test_preview_y_confirmacion(client, admin_headers, db_session, escenario):
    r = await _subir(client, admin_headers)
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["total"] == 3
    assert preview["listos"] == 3
    assert preview["alumnos"][1]["email_generado"] is True
    assert preview["alumnos"][1]["email"] == f"{CODIGOS[1]}@unamba.edu.pe"

    filas = [
        {
            "fila": alumno["fila"],
            "code": alumno["code"],
            "dni": alumno["dni"],
            "full_name": alumno["full_name"],
            "email": alumno["email"],
            "semester": alumno["semester"],
        }
        for alumno in preview["alumnos"]
    ]
    r = await client.post(
        f"{API}/students/import-confirm",
        headers=admin_headers,
        json={"alumnos": filas},
    )
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["creados"] == 3 and resultado["omitidos"] == 0
    assert resultado["errores"] == []

    usuarios = (
        await db_session.exec(select(AppUser).where(AppUser.code.in_(CODIGOS)))
    ).all()
    assert len(usuarios) == 3
    assert all(usuario.must_change_password for usuario in usuarios)
    assert all(usuario.semester == 2 for usuario in usuarios)

    r = await _subir(client, admin_headers)
    preview = r.json()
    assert all(alumno["duplicado"] for alumno in preview["alumnos"])
    r = await client.post(
        f"{API}/students/import-confirm",
        headers=admin_headers,
        json={"alumnos": filas},
    )
    assert r.status_code == 200
    assert r.json()["creados"] == 0 and r.json()["omitidos"] == 3

    audit = (
        await db_session.exec(
            select(AuditLog)
            .where(AuditLog.action == "importacion_alumnos_confirmada")
            .order_by(AuditLog.id.desc())
        )
    ).first()
    assert audit is not None
    assert set(audit.new_value) == {"creados", "omitidos", "matriculados", "errores"}


async def test_confirmacion_matricula_en_grupo(client, admin_headers, db_session, escenario):
    await _subir(client, admin_headers)
    r = await client.post(
        f"{API}/students/import-confirm",
        headers=admin_headers,
        json={
            "alumnos": [{
                "fila": 1, "code": CODIGOS[3], "dni": DNIS[3],
                "full_name": NOMBRES[3], "email": f"{CODIGOS[3]}@unamba.edu.pe",
                "semester": 2,
            }],
            "group_id": escenario["grupo_id"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["creados"] == 1 and r.json()["matriculados"] == 1
    usuario = (
        await db_session.exec(select(AppUser).where(AppUser.code == CODIGOS[3]))
    ).first()
    matricula = (
        await db_session.exec(
            select(Enrollment).where(
                Enrollment.student_id == usuario.id,
                Enrollment.group_id == escenario["grupo_id"],
            )
        )
    ).first()
    assert matricula is not None and matricula.withdrawn_at is None


async def test_confirmacion_reporta_fila_invalida(client, admin_headers, escenario):
    r = await client.post(
        f"{API}/students/import-confirm",
        headers=admin_headers,
        json={
            "alumnos": [{
                "fila": 1, "code": "123", "dni": "75551004",
                "full_name": "ALUMNO INVALIDO", "email": "123@unamba.edu.pe",
                "semester": 2,
            }]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["creados"] == 0
    assert data["errores"][0]["fila"] == 1
    assert "código" in data["errores"][0]["motivo"]


async def test_preview_rechaza_docente(client, docente_headers, escenario):
    r = await _subir(client, docente_headers)
    assert r.status_code == 403


async def test_preview_rechaza_archivo_grande(client, admin_headers):
    r = await _subir(
        client, admin_headers, contenido=b"x" * (10 * 1024 * 1024 + 1), nombre="grande.png"
    )
    assert r.status_code == 413
