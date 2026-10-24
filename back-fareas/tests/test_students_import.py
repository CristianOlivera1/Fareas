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


def _celda(texto: str, x: float, y: float, ancho: float = 100, alto: float = 18) -> ItemTexto:
    return ItemTexto(texto=texto, x=x, y=y, ancho=ancho, alto=alto, confianza=0.99, pagina=1)


def _documento(items: list[ItemTexto]) -> DocumentoLeido:
    return DocumentoLeido(tipo="imagen", paginas=1, items=items, lineas=agrupar_lineas(items))


def test_nomina_con_nombre_en_varias_lineas_y_cabecera_partida():
    items = [
        _celda("Nombre", 30, 10, 60), _celda("Completo", 30, 30, 70),
        _celda("Correo Institucional", 135, 30, 140), _celda("DNI", 370, 30, 32),
        _celda("Código", 445, 30, 60), _celda("Ciclo", 518, 30, 45),
        _celda("WhatsApp", 590, 30, 80),
        _celda("Altamirano", 30, 73, 80), _celda("Rojas,", 30, 96, 50),
        _celda("Carlos", 30, 118, 50), _celda("Manuel", 30, 141, 55),
        _celda("carlos.altamirano@unamba.edu.pe", 134, 76, 227),
        _celda("71948203", 364, 75, 74), _celda("222041", 446, 75, 52),
        _celda("一", 520, 76, 11), _celda("984712304", 591, 75, 76),
        _celda("Ramos", 30, 187, 60), _celda("Vilca, Luz", 30, 209, 70),
        _celda("Clarita", 30, 231, 60),
        _celda("I.ramos@unamba.edu.pe", 134, 190, 170),
        _celda("45910284", 370, 189, 68), _celda("221199", 446, 189, 55),
        _celda("ⅢII", 520, 190, 30), _celda("935612847", 590, 186, 78),
    ]
    alumnos = parsear_nomina(_documento(items), default_semester=9)
    assert [a.full_name for a in alumnos] == [
        "Altamirano Rojas, Carlos Manuel",
        "Ramos Vilca, Luz Clarita",
    ]
    assert [a.semester for a in alumnos] == [1, 3]
    assert [a.whatsapp for a in alumnos] == ["984712304", "935612847"]
    assert all(a.confiable and not a.errores for a in alumnos)


def test_nomina_apellidos_y_nombres_en_columnas_separadas_y_otro_orden():
    items = [
        _celda("Ciclo", 20, 10, 40), _celda("Nombres", 100, 10, 80),
        _celda("Apellido Paterno", 250, 10, 120), _celda("Apellido Materno", 400, 10, 120),
        _celda("DNI", 560, 10, 30), _celda("Código", 640, 10, 60),
        _celda("Correo", 740, 10, 60),
        _celda("IV", 20, 60, 20), _celda("Jhoel Franz", 100, 60, 110),
        _celda("Quispe", 250, 60, 60), _celda("Ccahuana", 400, 60, 80),
        _celda("70583921", 560, 60, 70), _celda("201147", 640, 60, 55),
        _celda("jhoel.quispe@unamba.edu.pe", 740, 60, 200),
    ]
    [alumno] = parsear_nomina(_documento(items), default_semester=1)
    assert alumno.full_name == "Quispe Ccahuana, Jhoel Franz"
    assert alumno.semester == 4
    assert alumno.code == "201147" and alumno.dni == "70583921"


def test_nomina_sin_cabecera_en_una_sola_linea_por_alumno():
    items = [
        _celda("1 222041 71948203 ALTAMIRANO ROJAS CARLOS carlos.a@unamba.edu.pe III +51 984-712-304", 10, 10, 900),
        _celda("2. 241032 46291048 CONDORI HUAMAN ANA 2do ciclo", 10, 50, 600),
    ]
    alumnos = parsear_nomina(_documento(items), default_semester=7)
    assert alumnos[0].full_name == "ALTAMIRANO ROJAS CARLOS"
    assert alumnos[0].semester == 3 and alumnos[0].whatsapp == "984712304"
    assert alumnos[0].email == "carlos.a@unamba.edu.pe"
    assert alumnos[1].full_name == "CONDORI HUAMAN ANA"
    assert alumnos[1].semester == 2 and alumnos[1].email_generado is True


def test_nomina_filas_pegadas_y_correo_partido():
    items = [
        _celda("Código", 10, 0, 60), _celda("DNI", 100, 0, 40), _celda("Alumno", 200, 0, 60),
        _celda("Correo", 420, 0, 60),
        _celda("111111", 10, 20), _celda("22222222", 100, 20), _celda("PEREZ, LUIS", 200, 20, 150),
        _celda("luis.perez@", 420, 20, 90), _celda("unamba.edu.pe", 420, 38, 110),
        _celda("333333", 10, 58), _celda("44444444", 100, 58), _celda("SOTO, ANA", 200, 58, 150),
        _celda("ana.soto@unamba.edu.pe", 420, 58, 180),
        _celda("555555", 10, 77), _celda("66666666", 100, 77), _celda("DIAZ, ROSA", 200, 77, 150),
    ]
    alumnos = parsear_nomina(_documento(items), default_semester=5)
    assert [a.email for a in alumnos] == [
        "luis.perez@unamba.edu.pe",
        "ana.soto@unamba.edu.pe",
        "555555@unamba.edu.pe",
    ]
    assert [a.full_name for a in alumnos] == ["PEREZ, LUIS", "SOTO, ANA", "DIAZ, ROSA"]
    assert alumnos[2].email_generado is True
    assert all(a.semester == 5 and a.nota for a in alumnos)


def test_nomina_ignora_titulo_con_palabras_de_cabecera():
    items = [
        _celda("NOMINA DE ALUMNOS 2026-II", 10, 0, 400),
        _celda("Código", 10, 60, 60), _celda("DNI", 100, 60, 40), _celda("Apellidos y Nombres", 200, 60, 200),
        _celda("999111", 10, 90), _celda("11112222", 100, 90), _celda("GARCIA, MARIA", 200, 90, 180),
        _celda("Total: 1 alumno", 10, 130, 150),
    ]
    [alumno] = parsear_nomina(_documento(items), default_semester=2)
    assert alumno.full_name == "GARCIA, MARIA"
