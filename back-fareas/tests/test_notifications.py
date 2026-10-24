from datetime import timedelta

import pytest
from sqlmodel import delete, select

from app.services.attendance_engine import cancelar_sesion, cerrar_sesion
from app.services.justifications import crear as crear_justificacion
from app.services.notification_center import (
    crear_notificaciones,
    despachar_correos_pendientes,
)
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    Notification,
    SessionStatus,
)
from tests.helpers_b6 import crear, limpiar

API = "/api/v1"


async def _user(db, email: str) -> AppUser:
    user = (await db.exec(select(AppUser).where(AppUser.email == email))).first()
    assert user is not None
    return user


@pytest.fixture(autouse=True)
async def _limpiar_notificaciones(db_session, temp_student):
    admin = await _user(db_session, "admin@unamba.edu.pe")
    ids = [temp_student.id, admin.id]
    await db_session.exec(delete(Notification).where(Notification.user_id.in_(ids)))
    await db_session.commit()
    yield
    await db_session.exec(delete(Notification).where(Notification.user_id.in_(ids)))
    await db_session.commit()


@pytest.fixture
async def student_headers(client, db_session, temp_student):
    temp_student.must_change_password = False
    db_session.add(temp_student)
    await db_session.commit()
    r = await client.post(
        f"{API}/auth/login",
        json={"email": "temp.student@unamba.edu.pe", "password": "ClaveTemporal1"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def escenario(db_session):
    await limpiar(db_session)
    esc = await crear(db_session)
    yield esc
    await limpiar(db_session)


async def test_contador_listado_y_lectura_por_usuario(
    client, db_session, student_headers, admin_headers, temp_student
):
    admin = await _user(db_session, "admin@unamba.edu.pe")
    await crear_notificaciones(
        db_session,
        user_ids=[temp_student.id],
        kind="prueba",
        title="Solo para el alumno",
        message="Contenido privado del alumno",
        email=False,
    )
    await crear_notificaciones(
        db_session,
        user_ids=[admin.id],
        kind="prueba",
        title="Solo para el admin",
        message="Contenido privado del admin",
        email=False,
    )
    await db_session.commit()

    r = await client.get(f"{API}/notifications/unread-count", headers=student_headers)
    assert r.status_code == 200 and r.json()["count"] == 1

    r = await client.get(f"{API}/notifications", headers=student_headers)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["unread"] == 1
    titulos = [n["title"] for n in cuerpo["items"]]
    assert "Solo para el alumno" in titulos and "Solo para el admin" not in titulos
    notif_id = next(n["id"] for n in cuerpo["items"] if n["title"] == "Solo para el alumno")

    admin_list = (
        await client.get(f"{API}/notifications", headers=admin_headers)
    ).json()["items"]
    admin_id = next(n["id"] for n in admin_list if n["title"] == "Solo para el admin")
    r = await client.post(f"{API}/notifications/{admin_id}/read", headers=student_headers)
    assert r.status_code == 404

    r = await client.post(f"{API}/notifications/{notif_id}/read", headers=student_headers)
    assert r.status_code == 200 and r.json()["count"] == 0

    r = await client.get(
        f"{API}/notifications", headers=student_headers, params={"unread_only": True}
    )
    assert r.status_code == 200 and r.json()["items"] == []

    r = await client.post(f"{API}/notifications/read-all", headers=student_headers)
    assert r.status_code == 200 and r.json()["count"] == 0


async def test_justificacion_notifica_estudiante_docente_y_admin(db_session, escenario):
    esc = escenario
    admin = await _user(db_session, "admin@unamba.edu.pe")
    docente = await db_session.get(AppUser, esc["docente_id"])
    alumno = await db_session.get(AppUser, esc["e2"])
    assert docente is not None and alumno is not None

    await crear_justificacion(
        db_session,
        admin,
        student_id=esc["e2"],
        course_id=esc["curso_id"],
        start_date=esc["lunes"],
        end_date=esc["lunes"],
        reason="Descanso médico presentado en secretaría",
    )

    filas = (
        await db_session.exec(
            select(Notification).where(
                Notification.user_id.in_([esc["e2"], esc["docente_id"], admin.id]),
                Notification.kind == "justificacion",
            )
        )
    ).all()
    por_usuario = {f.user_id: f for f in filas}
    assert esc["e2"] in por_usuario and "Justificación registrada" in por_usuario[esc["e2"]].title
    assert esc["docente_id"] in por_usuario and "Nueva justificación" in por_usuario[esc["docente_id"]].title
    assert admin.id not in por_usuario

    await crear_justificacion(
        db_session,
        docente,
        student_id=esc["e2"],
        course_id=esc["curso_id"],
        start_date=esc["lunes"] + timedelta(days=7),
        end_date=esc["lunes"] + timedelta(days=7),
        reason="Viaje académico autorizado por la facultad",
    )
    aviso_admin = (
        await db_session.exec(
            select(Notification).where(
                Notification.user_id == admin.id,
                Notification.kind == "justificacion",
            )
        )
    ).first()
    assert aviso_admin is not None
    assert "docente" in aviso_admin.title.lower()


async def test_clase_cancelada_notifica_estudiantes_y_docente(db_session, escenario):
    esc = escenario
    admin = await _user(db_session, "admin@unamba.edu.pe")
    sesion = AttendanceSession(
        block_id=esc["bloque_id"],
        session_date=esc["lunes"],
        status=SessionStatus.ABIERTA,
    )
    db_session.add(sesion)
    await db_session.commit()

    await cancelar_sesion(
        db_session, sesion, admin, "Paro de transporte en la ciudad"
    )

    filas = (
        await db_session.exec(
            select(Notification).where(
                Notification.user_id.in_([esc["e1"], esc["e2"], esc["docente_id"]]),
                Notification.kind == "clase_cancelada",
            )
        )
    ).all()
    assert {f.user_id for f in filas} == {esc["e1"], esc["e2"], esc["docente_id"]}
    assert all(f.email_status == "pending" for f in filas)
    assert all("cancelada" in f.message.lower() for f in filas)


async def test_sesion_sin_marcas_notifica_revision(db_session, escenario):
    esc = escenario
    admin = await _user(db_session, "admin@unamba.edu.pe")
    sesion = AttendanceSession(
        block_id=esc["bloque_id"],
        session_date=esc["lunes"],
        status=SessionStatus.ABIERTA,
    )
    db_session.add(sesion)
    await db_session.commit()

    resultado = await cerrar_sesion(db_session, sesion, actor=None)
    assert resultado["status"] == "needs_review"

    filas = (
        await db_session.exec(
            select(Notification).where(Notification.dedupe_key == f"review:{sesion.id}")
        )
    ).all()
    assert {f.user_id for f in filas} == {esc["docente_id"], admin.id}
    assert all(f.kind == "sesion_revision" and f.email_status == "pending" for f in filas)


async def test_rectificacion_notifica_al_estudiante(
    client, admin_headers, db_session, escenario
):
    esc = escenario
    sesion = AttendanceSession(
        block_id=esc["bloque_id"],
        session_date=esc["lunes"],
        status=SessionStatus.CERRADA,
    )
    db_session.add(sesion)
    await db_session.flush()
    record = AttendanceRecord(
        session_id=sesion.id,
        student_id=esc["e1"],
        status="falta",
        method="facial",
    )
    db_session.add(record)
    await db_session.commit()

    r = await client.patch(
        f"{API}/attendance/{record.id}/rectify",
        headers=admin_headers,
        json={"new_status": "asistio", "reason": "Corrección administrativa verificada"},
    )
    assert r.status_code == 200, r.text

    aviso = (
        await db_session.exec(
            select(Notification).where(
                Notification.user_id == esc["e1"],
                Notification.kind == "rectificacion",
            )
        )
    ).first()
    assert aviso is not None
    assert aviso.email_status == "pending"
    assert "falta" in aviso.message and "asistio" in aviso.message


async def test_cola_de_correo_marca_enviado(
    db_session, temp_student, monkeypatch: pytest.MonkeyPatch
):
    await db_session.exec(delete(Notification).where(Notification.email_status == "pending"))
    await db_session.commit()

    await crear_notificaciones(
        db_session,
        user_ids=[temp_student.id],
        kind="correo",
        title="Aviso de prueba",
        message="Este correo sale de la cola",
        link="/admin/me",
        email=True,
        dedupe_key="test-cola-correo",
    )
    await db_session.commit()

    enviados: list[tuple] = []

    async def _fake(*args, **kwargs) -> bool:
        enviados.append((args, kwargs))
        return True

    class _Settings:
        MAIL_ENABLED = True

    from app.services import notification_center

    monkeypatch.setattr(notification_center, "send_notification_email", _fake)
    monkeypatch.setattr(notification_center, "get_settings", lambda: _Settings())

    assert await despachar_correos_pendientes(limit=1) == 1
    fila = (
        await db_session.exec(
            select(Notification).where(Notification.dedupe_key == "test-cola-correo")
        )
    ).first()
    assert fila is not None and fila.email_status == "sent"
    assert fila.email_sent_at is not None and fila.email_error is None
    assert enviados and enviados[0][0][2] == "Aviso de prueba"
