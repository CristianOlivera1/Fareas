import asyncio
import sys
from datetime import time

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import get_settings
from app.database import engine
from app.services.attendance_engine import ahora_peru, _naive_peru
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    Course,
    CourseGroup,
    Enrollment,
    Justification,
    Room,
    ScheduleBlock,
    SessionStatus,
    UserRole,
)

PREFIX = "ZZF3"


async def _ctx() -> SQLModelAsyncSession:
    settings = get_settings()
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=SQLModelAsyncSession)
    _ = settings
    return maker()

async def create() -> None:
    db = await _ctx()
    hoy = _naive_peru(ahora_peru()).date()
    assert hoy.isoweekday() <= 5, (
        f"Hoy es {hoy} (día {hoy.isoweekday()}): el fixture crea sesiones DE HOY y la "
        "semana lectiva es Lunes-Viernes. Corre este fixture un día de semana."
    )
    teacher = (await db.exec(select(AppUser).where(AppUser.role == UserRole.DOCENTE))).first()
    admin = (await db.exec(select(AppUser).where(AppUser.role == UserRole.ADMIN))).first()
    room = (await db.exec(select(Room).where(Room.is_active))).first()
    assert admin and room, "se necesita un admin y un aula del seed"

    course = Course(code=f"{PREFIX}01", name="Fixture F3 (temporal) — borrar", cycle=9)
    db.add(course)
    await db.flush()

    group = CourseGroup(
        course_id=course.id, group_code="Z", teacher_id=teacher.id if teacher else admin.id,
        semester_label="2026-II", capacity=40,
    )
    db.add(group)
    await db.flush()

    bloques = []
    for i, inicio in enumerate([time(22, 0), time(10, 0), time(16, 0)]):
        b = ScheduleBlock(group_id=group.id, room_id=room.id, weekday=hoy.isoweekday(),
                          start_time=inicio, end_time=time(inicio.hour + 1, 0))
        db.add(b)
        await db.flush()
        bloques.append(b)

    cuentas = []
    for n in (1, 2):
        u = AppUser(
            role=UserRole.ESTUDIANTE, code=f"{PREFIX}0{n}", dni=f"99{n}0000{n}",
            email=f"f3.fixture{n}@unamba.edu.pe", full_name=f"Alumno F3 #{n}",
            password_hash=admin.password_hash, must_change_password=False, semester=6,
        )
        db.add(u)
        await db.flush()
        db.add(Enrollment(student_id=u.id, group_id=group.id))
        cuentas.append(u)

    sesion_abierta = AttendanceSession(block_id=bloques[0].id, session_date=hoy,
                                       status=SessionStatus.ABIERTA)
    revision_confirmar = AttendanceSession(block_id=bloques[1].id, session_date=hoy,
                                           status=SessionStatus.CERRADA, needs_review=True,
                                           closed_at=_naive_peru(ahora_peru()))
    revision_cancelar = AttendanceSession(block_id=bloques[2].id, session_date=hoy,
                                          status=SessionStatus.CERRADA, needs_review=True,
                                          closed_at=_naive_peru(ahora_peru()))
    for s in (sesion_abierta, revision_confirmar, revision_cancelar):
        db.add(s)
    await db.commit()

    print(f"OK hoy={hoy} course={course.id} group={group.id} "
          f"students={[u.id for u in cuentas]} sess_abierta={sesion_abierta.id} "
          f"sess_review_confirm={revision_confirmar.id} sess_review_cancel={revision_cancelar.id}")

async def cleanup() -> None:
    db = await _ctx()
    course_ids = [c.id for c in (await db.exec(select(Course).where(Course.code == f"{PREFIX}01"))).all()]
    users = (await db.exec(select(AppUser).where(AppUser.code.like(f"{PREFIX}%")))).all()
    user_ids = [u.id for u in users]
    groups = (await db.exec(select(CourseGroup).where(CourseGroup.course_id.in_(course_ids)))).all()
    group_ids = [g.id for g in groups]
    blocks = (await db.exec(select(ScheduleBlock).where(ScheduleBlock.group_id.in_(group_ids)))).all()
    block_ids = [b.id for b in blocks]
    sessions = (await db.exec(select(AttendanceSession).where(AttendanceSession.block_id.in_(block_ids)))).all()
    session_ids = [s.id for s in sessions]

    records = (await db.exec(select(AttendanceRecord).where(AttendanceRecord.session_id.in_(session_ids)))).all()
    for r in records:
        await db.delete(r)
    for s in sessions:
        await db.delete(s)
    justifs = (await db.exec(select(Justification).where(Justification.student_id.in_(user_ids)))).all()
    for j in justifs:
        await db.delete(j)
    for b in blocks:
        await db.delete(b)
    enrolls = (await db.exec(select(Enrollment).where(Enrollment.group_id.in_(group_ids)))).all()
    for e in enrolls:
        await db.delete(e)
    for g in groups:
        await db.delete(g)
    for u in users:
        await db.delete(u)
    courses = (await db.exec(select(Course).where(Course.id.in_(course_ids)))).all()
    for c in courses:
        await db.delete(c)
    await db.commit()
    print(f"OK limpiado: {len(records)} registros, {len(sessions)} sesiones, {len(justifs)} justificaciones, "
          f"{len(blocks)} bloques, {len(enrolls)} matrículas, {len(groups)} grupos, {len(users)} alumnos, "
          f"{len(courses)} cursos")

if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "create"
    asyncio.run(create() if accion == "create" else cleanup())
