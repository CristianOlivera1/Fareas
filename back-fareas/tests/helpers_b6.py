"""Escenario compartido del Bloque 6: aula+curso+grupo+bloque LUN 08:00-10:00.

Crea todo temporal (TST-/temp.*.b6) y lo limpia por IDs explícitos.
"""
from datetime import date, datetime, timedelta

from sqlmodel import delete, select

from app.services.attendance_engine import PERU_TZ
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    Course,
    CourseGroup,
    Device,
    Enrollment,
    Holiday,
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
    """El lunes SIGUIENTE al base (o el mismo día si base es lunes)."""
    return base if base.isoweekday() == 1 else base + timedelta(days=(8 - base.isoweekday()) % 7 or 7)


def h(lunes: date, hhmm: str) -> datetime:
    """aware UTC-5 en el lunes del escenario a la hora dada."""
    hh, mm = map(int, hhmm.split(":"))
    return datetime(lunes.year, lunes.month, lunes.day, hh, mm, tzinfo=PERU_TZ)


async def limpiar(db) -> None:
    """Borra el escenario en orden inverso de dependencias (por IDs)."""
    aula = (await db.exec(select(Room).where(Room.code == AULA))).first()
    if aula is not None:
        grupo_ids = (await db.exec(select(CourseGroup.id).where(CourseGroup.room_id == aula.id))).all()
        if grupo_ids:
            bloque_ids = (
                await db.exec(select(ScheduleBlock.id).where(ScheduleBlock.group_id.in_(grupo_ids)))  # type: ignore[attr-defined]
            ).all()
            if bloque_ids:
                ses_ids = (
                    await db.exec(
                        select(AttendanceSession.id).where(AttendanceSession.block_id.in_(bloque_ids))  # type: ignore[attr-defined]
                    )
                ).all()
                if ses_ids:
                    await db.exec(delete(AttendanceRecord).where(AttendanceRecord.session_id.in_(ses_ids)))  # type: ignore[attr-defined]
                    await db.exec(delete(AttendanceSession).where(AttendanceSession.id.in_(ses_ids)))  # type: ignore[attr-defined]
                await db.exec(delete(ScheduleBlock).where(ScheduleBlock.id.in_(bloque_ids)))  # type: ignore[attr-defined]
            await db.exec(delete(Enrollment).where(Enrollment.group_id.in_(grupo_ids)))  # type: ignore[attr-defined]
            await db.exec(delete(CourseGroup).where(CourseGroup.id.in_(grupo_ids)))  # type: ignore[attr-defined]
        await db.exec(delete(Device).where(Device.room_id == aula.id))  # type: ignore[attr-defined]
        await db.delete(aula)
    curso = (await db.exec(select(Course).where(Course.code == CURSO))).first()
    if curso is not None:
        await db.delete(curso)
    for email in (DOCENTE, EST1, EST2):
        user = (await db.exec(select(AppUser).where(AppUser.email == email))).first()
        if user is not None:
            await db.delete(user)
    await db.exec(delete(Holiday).where(Holiday.description == FERIADO_DESC))  # type: ignore[arg-type]
    await db.commit()


async def crear(db) -> dict:
    """Crea aula/curso/docente/2 estudiantes/grupo/bloque LUN 08:00-10:00."""
    aula = Room(code=AULA, name="Aula de pruebas B6")
    curso = Course(code=CURSO, name="Curso de pruebas B6")
    docente = AppUser(role=UserRole.DOCENTE, email=DOCENTE, full_name="Docente B6",
                      password_hash="x" * 20, must_change_password=False, dni="74444000")
    e1 = AppUser(role=UserRole.ESTUDIANTE, email=EST1, code="996001",
                 full_name="Estudiante Uno B6", password_hash="x" * 20, semester=5, dni="74444001")
    e2 = AppUser(role=UserRole.ESTUDIANTE, email=EST2, code="996002",
                 full_name="Estudiante Dos B6", password_hash="x" * 20, semester=5, dni="74444002")
    db.add_all([aula, curso, docente, e1, e2])
    await db.flush()

    grupo = CourseGroup(course_id=curso.id, group_code="A", teacher_id=docente.id, room_id=aula.id)
    db.add(grupo)
    await db.flush()
    bloque = ScheduleBlock(
        group_id=grupo.id, weekday=1,
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
