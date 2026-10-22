from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import UserDefinedType
from sqlmodel import Column, Field, SQLModel
from sqlmodel import Enum as SAEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    DOCENTE = "docente"
    ESTUDIANTE = "estudiante"

class AttendanceStatus(StrEnum):
    ASISTIO = "asistio"
    TARDANZA = "tardanza"
    FALTA = "falta"

class SessionStatus(StrEnum):
    ABIERTA = "abierta"
    CERRADA = "cerrada"
    CANCELADA = "cancelada"

class DeviceType(StrEnum):
    CAMARA = "camara"
    ESP32 = "esp32"

def pg_enum(enum_cls: type[StrEnum], name: str) -> Column:
    return Column(
        SAEnum(
            enum_cls,
            name=name,
            native_enum=True,
            create_type=False,
            values_callable=lambda cls: [e.value for e in cls],
        )
    )

def server_now_kwargs() -> dict:
    return {"sa_column_kwargs": {"server_default": text("now()")}}

class AppSettings(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int | None = Field(default=1, primary_key=True)
    semester_label: str = Field(max_length=40)
    semester_start: date | None = None
    semester_end: date | None = None
    block_minutes: int = 120
    late_tolerance_minutes: int = 10
    early_open_minutes: int = 15
    rectify_days: int = 7
    dpi_min_sessions: int = 4
    face_match_threshold: Decimal = Field(default=Decimal("0.750"), max_digits=4, decimal_places=3)
    dpi_alert_percent: Decimal = Field(default=Decimal("20.00"), max_digits=5, decimal_places=2)
    dpi_limit_percent: Decimal = Field(default=Decimal("30.00"), max_digits=5, decimal_places=2)
    attendance_hour_start: time = time(7, 0)
    attendance_hour_end: time = time(20, 0)
    updated_at: datetime | None = Field(default=None, **server_now_kwargs())

class AppUser(SQLModel, table=True):
    __tablename__ = "app_user"

    id: int | None = Field(default=None, primary_key=True)
    role: UserRole = Field(sa_column=pg_enum(UserRole, "user_role"))
    dni: str | None = Field(default=None, max_length=12)
    code: str | None = Field(default=None, max_length=20)
    email: str = Field(max_length=160, unique=True)
    full_name: str = Field(max_length=160)
    whatsapp: str | None = Field(default=None, max_length=20)
    password_hash: str = Field(max_length=128)
    must_change_password: bool = True
    semester: int | None = None
    is_active: bool = True
    token_version: int = 0
    face_consent_at: datetime | None = None
    created_at: datetime | None = Field(default=None, **server_now_kwargs())
    updated_at: datetime | None = Field(default=None, **server_now_kwargs())

class Room(SQLModel, table=True):
    __tablename__ = "room"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=20, unique=True)
    name: str | None = Field(default=None, max_length=120)
    building: str | None = Field(default=None, max_length=80)
    capacity: int | None = None
    is_active: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class Device(SQLModel, table=True):
    __tablename__ = "device"

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id")
    device_type: DeviceType = Field(sa_column=pg_enum(DeviceType, "device_type"))
    device_key: str = Field(max_length=64, unique=True)
    name: str | None = Field(default=None, max_length=80)
    ip_address: str | None = Field(default=None, max_length=45)
    mac_address: str | None = Field(default=None, max_length=17)
    rtsp_url: str | None = Field(default=None, max_length=255)
    is_online: bool = False
    last_heartbeat: datetime | None = None
    is_active: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class Course(SQLModel, table=True):
    __tablename__ = "course"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=20, unique=True)
    name: str = Field(max_length=160)
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class CourseGroup(SQLModel, table=True):
    __tablename__ = "course_group"

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id")
    group_code: str = Field(max_length=5)
    teacher_id: int = Field(foreign_key="app_user.id")
    semester_label: str = Field(max_length=40)
    capacity: int = 40
    is_active: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class ScheduleBlock(SQLModel, table=True):
    __tablename__ = "schedule_block"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="course_group.id")
    weekday: int = Field(ge=1, le=5)
    start_time: time
    end_time: time
    room_id: int = Field(foreign_key="room.id")

class Enrollment(SQLModel, table=True):
    __tablename__ = "enrollment"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="app_user.id")
    group_id: int = Field(foreign_key="course_group.id")
    enrolled_at: datetime | None = Field(default=None, **server_now_kwargs())
    withdrawn_at: datetime | None = None

class PgRealArray(UserDefinedType):
    cache_ok = True

    def get_col_spec(self) -> str:
        return "REAL[]"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return [float(x) for x in value]

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            return value

        return process

class FaceEmbedding(SQLModel, table=True):
    __tablename__ = "face_embedding"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="app_user.id")
    vector: Any = Field(default=None, sa_column=Column(PgRealArray()))
    photo_url: str | None = Field(default=None, max_length=500)
    source: str = Field(default="upload", max_length=20)
    is_current: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class Holiday(SQLModel, table=True):
    __tablename__ = "holiday"

    id: int | None = Field(default=None, primary_key=True)
    holiday_date: date = Field(unique=True)
    description: str = Field(max_length=160)
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class Justification(SQLModel, table=True):
    __tablename__ = "justification"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="app_user.id")
    course_id: int | None = Field(default=None, foreign_key="course.id")
    start_date: date
    end_date: date
    reason: str = Field(max_length=400)
    document_url: str | None = Field(default=None, max_length=500)
    created_by: int = Field(foreign_key="app_user.id")
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class AttendanceSession(SQLModel, table=True):
    __tablename__ = "attendance_session"

    id: int | None = Field(default=None, primary_key=True)
    block_id: int = Field(foreign_key="schedule_block.id")
    session_date: date
    status: SessionStatus = Field(default=SessionStatus.ABIERTA, sa_column=pg_enum(SessionStatus, "session_status"))
    opened_at: datetime | None = Field(default=None, **server_now_kwargs())
    closed_at: datetime | None = None
    needs_review: bool = False
    cancel_reason: str | None = Field(default=None, max_length=200)
    cancelled_by: int | None = Field(default=None, foreign_key="app_user.id")
    cancelled_at: datetime | None = None

class AttendanceRecord(SQLModel, table=True):
    __tablename__ = "attendance_record"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="attendance_session.id")
    student_id: int = Field(foreign_key="app_user.id")
    status: AttendanceStatus = Field(sa_column=pg_enum(AttendanceStatus, "attendance_status"))
    marked_at: datetime | None = None
    method: str = Field(default="facial", max_length=10)
    similarity: Decimal | None = Field(default=None, max_digits=5, decimal_places=4)
    corrected_by: int | None = Field(default=None, foreign_key="app_user.id")
    corrected_at: datetime | None = None
    correct_reason: str | None = Field(default=None, max_length=400)
    is_justified: bool = False
    justification_id: int | None = Field(default=None, foreign_key="justification.id")
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    actor_id: int | None = Field(default=None, foreign_key="app_user.id")
    action: str = Field(max_length=40)
    entity: str = Field(max_length=40)
    entity_id: int | None = None
    old_value: dict | list | None = Field(default=None, sa_column=Column(JSONB))
    new_value: dict | list | None = Field(default=None, sa_column=Column(JSONB))
    ip_address: str | None = Field(default=None, max_length=45)
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

class DpiAlertSent(SQLModel, table=True):
    __tablename__ = "dpi_alert_sent"

    student_id: int = Field(foreign_key="app_user.id", primary_key=True)
    course_id: int = Field(foreign_key="course.id", primary_key=True)
    semester_label: str = Field(max_length=40, primary_key=True)
    level: str = Field(max_length=10, primary_key=True)
    sent_at: datetime | None = Field(default=None, **server_now_kwargs())
