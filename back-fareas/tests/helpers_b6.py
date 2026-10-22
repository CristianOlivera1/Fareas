from datetime import date, datetime, timedelta

import pytest
from sqlmodel import delete, select

from app.services.attendance_engine import PERU_TZ
from app.tables import (
    AppSettings,
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    AuditLog,
    Course,
    CourseGroup,
    Device,
    Enrollment,
    Holiday,
    Justification,
    Room,
    ScheduleBlock,
    UserRole,
)

AULA = "TST-AULA-B6"
CURSO = "TST601"
DOCENTE = "temp.docente.b6@unamba.edu.pe"
EST1 = "temp.est1.b6@unamba.edu.pe"
EST2 = "temp.est2.b6@unamba.edu.pe"
FERIADO_DESC = "Feriado test B6"


def proximo_lunes(base: date) -> date:
    return base if base.isoweekday() == 1 else base + timedelta(days=(8 - base.isoweekday()) % 7 or 7)

def weekday_hoy() -> int:
    wd = datetime.now(PERU_TZ).date().isoweekday()
    if wd > 5:
        pytest.skip("Fin de semana: no hay clases hoy (weekday 1..5) — escenario 'de hoy' imposible")
    return wd

def h(lunes: date, hhmm: str) -> datetime:
    hh, mm = map(int, hhmm.split(":"))
    return datetime(lunes.year, lunes.month, lunes.day, hh, mm, tzinfo=PERU_TZ)

async def limpiar(db) -> None:
    actores = [
        u.id
        for email in (DOCENTE, EST1, EST2)
        if (u := (await db.exec(select(AppUser).where(AppUser.email == email))).first()) is not None
    ]
    if actores:
        await db.exec(delete(Justification).where(Justification.student_id.in_(actores)))
        await db.exec(delete(Justification).where(Justification.created_by.in_(actores)))
        await db.commit()
    curso = (await db.exec(select(Course).where(Course.code == CURSO))).first()
    aula = (await db.exec(select(Room).where(Room.code == AULA))).first()
    grupo_ids: set[int] = set()
    if curso is not None:
        grupo_ids |= {
            gid
            for gid in (
                await db.exec(select(CourseGroup.id).where(CourseGroup.course_id == curso.id))
            ).all()
        }
    if aula is not None:
        grupo_ids |= {
            gid
            for gid in (
                await db.exec(
                    select(ScheduleBlock.group_id).where(ScheduleBlock.room_id == aula.id)
                )
            ).all()
        }
    ids = list(grupo_ids)
    if ids:
        bloque_ids = (
            await db.exec(select(ScheduleBlock.id).where(ScheduleBlock.group_id.in_(ids)))
        ).all()
        if bloque_ids:
            ses_ids = (
                await db.exec(
                    select(AttendanceSession.id).where(AttendanceSession.block_id.in_(bloque_ids))
                )
            ).all()
            if ses_ids:
                await db.exec(delete(AttendanceRecord).where(AttendanceRecord.session_id.in_(ses_ids)))
                await db.exec(delete(AttendanceSession).where(AttendanceSession.id.in_(ses_ids)))
            await db.exec(delete(ScheduleBlock).where(ScheduleBlock.id.in_(bloque_ids)))
        await db.exec(delete(Enrollment).where(Enrollment.group_id.in_(ids)))
        await db.exec(delete(CourseGroup).where(CourseGroup.id.in_(ids)))
    if aula is not None:
        await db.exec(delete(Device).where(Device.room_id == aula.id))
        await db.delete(aula)
    if curso is not None:
        await db.delete(curso)
    for email in (DOCENTE, EST1, EST2):
        user = (await db.exec(select(AppUser).where(AppUser.email == email))).first()
        if user is not None:
            await db.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))
            await db.delete(user)
    await db.exec(delete(Holiday).where(Holiday.description == FERIADO_DESC))
    await db.commit()

async def crear(db) -> dict:
    aula = Room(code=AULA, name="Aula de pruebas B6")
    curso = Course(code=CURSO, name="Curso de pruebas B6")
    docente = AppUser(role=UserRole.DOCENTE, email=DOCENTE, full_name="Docente B6",
                      password_hash="x" * 20, must_change_password=False, dni="74444000")
    e1 = AppUser(role=UserRole.ESTUDIANTE, email=EST1, code="996001",
                 full_name="Estudiante Uno B6", password_hash="x" * 20, semester=5,
                 must_change_password=False, dni="74444001")
    e2 = AppUser(role=UserRole.ESTUDIANTE, email=EST2, code="996002",
                 full_name="Estudiante Dos B6", password_hash="x" * 20, semester=5,
                 must_change_password=False, dni="74444002")
    db.add_all([aula, curso, docente, e1, e2])
    await db.flush()

    cfg = await db.get(AppSettings, 1)
    semestre = cfg.semester_label if cfg is not None else "2026-I"
    grupo = CourseGroup(course_id=curso.id, group_code="A", teacher_id=docente.id,
                        semester_label=semestre)
    db.add(grupo)
    await db.flush()
    bloque = ScheduleBlock(
        group_id=grupo.id, room_id=aula.id, weekday=1,
        start_time=datetime.strptime("08:00", "%H:%M").time(),
        end_time=datetime.strptime("10:00", "%H:%M").time(),
    )
    db.add(bloque)
    db.add_all([Enrollment(student_id=e1.id, group_id=grupo.id),
                Enrollment(student_id=e2.id, group_id=grupo.id),
                Device(room_id=aula.id, device_type="camara", device_key="cam-tst-b6",
                       name="Cam B6", rtsp_url="rtsp://demo.invalido/stream")])
    await db.commit()

    return {
        "aula_id": aula.id, "curso_id": curso.id, "grupo_id": grupo.id,
        "bloque_id": bloque.id, "docente_id": docente.id, "e1": e1.id, "e2": e2.id,
        "lunes": proximo_lunes(datetime.now(PERU_TZ).date()),
    }
