"""Entidades SQLModel que MAPEAN las tablas creadas por back-fareas/db/001_schema.sql.

Regla del proyecto: la base de datos manda. Este módulo NUNCA ejecuta
create_all() ni genera DDL - cualquier cambio de esquema se hace en
back-fareas/db/001_schema.sql (la foto vigente de la BD), acompañado de un
ALTER nuevo (db/003_xxx.sql …) para las BD ya existentes y de su borrado
cuando todo el equipo lo aplicó (ver README >> "Actualizaciones de la base
de datos").

IMPORTANTE: las columnas con DEFAULT NOW() se declaran con server_default
para que SQLAlchemy las OMITA del INSERT y el valor lo genere PostgreSQL
(sin esto, el ORM envía NULL explícito y viola el NOT NULL).

Enums PostgreSQL nativos (creados en 001_schema.sql):
  user_role         : 'admin' | 'docente' | 'estudiante'          (RF-01)
  attendance_status : 'asistio' | 'tardanza' | 'falta'            (RF-23)
  session_status    : 'abierta' | 'cerrada' | 'cancelada'         (RF-26, R5)
  device_type       : 'camara' | 'esp32'                          (RF-05)

Los StrEnum de Python comparten los valores exactos de los enums de PG.
"""
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
    CANCELADA = "cancelada"  # R5: no genera faltas ni cuenta en DPI


class DeviceType(StrEnum):
    CAMARA = "camara"
    ESP32 = "esp32"


def pg_enum(enum_cls: type[StrEnum], name: str) -> Column:
    """Columna de enum PostgreSQL existente (create_type=False: ya está en la BD).

    values_callable es OBLIGATORIO: sin él SQLAlchemy vincula los NOMBRES de los
    miembros ('ESTUDIANTE') en lugar de los valores ('estudiante') y PostgreSQL
    rechaza el bind ('la sintaxis de entrada no es válida para el enum').
    """
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
    """Kwargs para columnas DEFAULT NOW(): el valor lo genera la BD, no el ORM."""
    return {"sa_column_kwargs": {"server_default": text("now()")}}


# app_settings (RF-34) - fila única id=1. block_minutes quedó INFORMATIVO
# (Bloque 11): la duración real sale de start_time/end_time de cada bloque.
class AppSettings(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int | None = Field(default=1, primary_key=True)
    semester_label: str = Field(max_length=40)
    semester_start: date | None = None  # R1: si ambas fechas son NULL no se restringe
    semester_end: date | None = None
    block_minutes: int = 120  # informativo: sugerencia para crear bloques de 1 h/2 h
    late_tolerance_minutes: int = 10
    early_open_minutes: int = 15  # R2/R3: apertura anticipada de la sesión
    rectify_days: int = 7  # R11: plazo del docente para rectificar
    dpi_min_sessions: int = 4  # R7: mínimo de sesiones antes de enviar alertas
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
    code: str | None = Field(default=None, max_length=20)  # código de matrícula
    email: str = Field(max_length=160, unique=True)
    full_name: str = Field(max_length=160)
    whatsapp: str | None = Field(default=None, max_length=20)
    password_hash: str = Field(max_length=128)
    must_change_password: bool = True  # RF-11: clave temporal obliga a cambiar
    semester: int | None = None  # ciclo del estudiante
    is_active: bool = True
    token_version: int = 0  # invalida JWT viejos tras cambiar la contraseña
    face_consent_at: datetime | None = None  # R13 (Ley 29733): consentimiento biométrico
    created_at: datetime | None = Field(default=None, **server_now_kwargs())
    updated_at: datetime | None = Field(default=None, **server_now_kwargs())


class Room(SQLModel, table=True):
    __tablename__ = "room"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=20, unique=True)  # 'LAB 304'
    name: str | None = Field(default=None, max_length=120)
    building: str | None = Field(default=None, max_length=80)
    capacity: int | None = None  # R9: aforo informativo del aula
    is_active: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())


class Device(SQLModel, table=True):
    __tablename__ = "device"

    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id")
    device_type: DeviceType = Field(sa_column=pg_enum(DeviceType, "device_type"))
    device_key: str = Field(max_length=64, unique=True)  # 'esp32-lab305'
    name: str | None = Field(default=None, max_length=80)
    ip_address: str | None = Field(default=None, max_length=45)
    mac_address: str | None = Field(default=None, max_length=17)
    rtsp_url: str | None = Field(default=None, max_length=255)  # solo cámaras
    is_online: bool = False  # RF-35
    last_heartbeat: datetime | None = None  # RF-33
    is_active: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())


class Course(SQLModel, table=True):
    __tablename__ = "course"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=20, unique=True)  # 'ISA903'
    name: str = Field(max_length=160)
    created_at: datetime | None = Field(default=None, **server_now_kwargs())


class CourseGroup(SQLModel, table=True):
    __tablename__ = "course_group"

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id")
    group_code: str = Field(max_length=5)  # 'A' | 'B' | 'C'
    teacher_id: int = Field(foreign_key="app_user.id")
    semester_label: str = Field(max_length=40)  # R1/R9: la unicidad incluye el semestre
    capacity: int = 40  # R8: cupo por defecto (decisión: 40 para todos los cursos)
    is_active: bool = True
    created_at: datetime | None = Field(default=None, **server_now_kwargs())


class ScheduleBlock(SQLModel, table=True):
    """Bloque horario de un grupo con SU AULA (R9/RF-06): el mismo grupo puede
    dictar en labs distintos según el día, por eso el aula vive aquí y no en el
    grupo (que solo guarda la sugerida)."""

    __tablename__ = "schedule_block"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="course_group.id")
    weekday: int = Field(ge=1, le=5)  # 1=Lunes … 5=Viernes (semana lectiva)
    start_time: time
    end_time: time
    room_id: int = Field(foreign_key="room.id")  # aula donde se dicta ESTE bloque


# enrollment (RF-03, RF-22) - retiro con withdrawn_at (R8): si hay registros la
# fila se retira (soft); si no, el servicio la borra. UNIQUE(student_id, group_id)
# se mantiene: re-matricular en el mismo grupo = withdrawn_at=None (reactivar).
class Enrollment(SQLModel, table=True):
    __tablename__ = "enrollment"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="app_user.id")
    group_id: int = Field(foreign_key="course_group.id")
    enrolled_at: datetime | None = Field(default=None, **server_now_kwargs())
    withdrawn_at: datetime | None = None


# face_embedding (RF-04, RF-19) - REAL[512], búsqueda coseno en NumPy (sin pgvector)
class PgRealArray(UserDefinedType):
    """Columna REAL[] de PostgreSQL (vector de embeddings de 512 dimensiones).

    Con asyncpg hay que pasar una LISTA de floats (un literal str '{0.1,...}'
    falla con DatatypeMismatch); a la lectura asyncpg ya entrega list[float].
    El moldeado a float32 se hace en la capa de servicio (NumPy).
    """

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
            return value  # asyncpg entrega list[float] nativo

        return process


class FaceEmbedding(SQLModel, table=True):
    __tablename__ = "face_embedding"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="app_user.id")
    vector: Any = Field(default=None, sa_column=Column(PgRealArray()))  # list[float] / np.ndarray
    photo_url: str | None = Field(default=None, max_length=500)
    source: str = Field(default="upload", max_length=20)  # 'upload' | 'promedio'
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
    course_id: int | None = Field(default=None, foreign_key="course.id")  # NULL = todos
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
    closed_at: datetime | None = None  # hora real de cierre (puede ser diferida)
    needs_review: bool = False  # R4: cerró con cero marcas → revisar antes de contar
    cancel_reason: str | None = Field(default=None, max_length=200)  # R5
    cancelled_by: int | None = Field(default=None, foreign_key="app_user.id")
    cancelled_at: datetime | None = None


class AttendanceRecord(SQLModel, table=True):
    __tablename__ = "attendance_record"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="attendance_session.id")
    student_id: int = Field(foreign_key="app_user.id")
    status: AttendanceStatus = Field(sa_column=pg_enum(AttendanceStatus, "attendance_status"))
    marked_at: datetime | None = None  # RF-21; NULL = falta generada por cierre (RF-26)
    method: str = Field(default="facial", max_length=10)  # 'facial' | 'manual'
    similarity: Decimal | None = Field(default=None, max_digits=5, decimal_places=4)  # RF-20
    corrected_by: int | None = Field(default=None, foreign_key="app_user.id")  # RF-15
    corrected_at: datetime | None = None
    correct_reason: str | None = Field(default=None, max_length=400)
    is_justified: bool = False  # R6: falta justificada (no cuenta para DPI)
    justification_id: int | None = Field(default=None, foreign_key="justification.id")
    created_at: datetime | None = Field(default=None, **server_now_kwargs())


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    actor_id: int | None = Field(default=None, foreign_key="app_user.id")  # NULL = sistema
    action: str = Field(max_length=40)   # 'rectificacion', 'credenciales_reenviadas', …
    entity: str = Field(max_length=40)   # 'attendance_record', 'app_user', …
    entity_id: int | None = None
    old_value: dict | list | None = Field(default=None, sa_column=Column(JSONB))
    new_value: dict | list | None = Field(default=None, sa_column=Column(JSONB))
    ip_address: str | None = Field(default=None, max_length=45)
    created_at: datetime | None = Field(default=None, **server_now_kwargs())

# dpi_alert_sent (R7, 001_schema.sql): UN correo por nivel (alerta/limite) por
# alumno-curso-semestre. El servicio inserta primero (ON CONFLICT DO NOTHING):
# si no insertó, ya se envió antes y no se repite.
class DpiAlertSent(SQLModel, table=True):
    __tablename__ = "dpi_alert_sent"

    student_id: int = Field(foreign_key="app_user.id", primary_key=True)
    course_id: int = Field(foreign_key="course.id", primary_key=True)
    semester_label: str = Field(max_length=40, primary_key=True)
    level: str = Field(max_length=10, primary_key=True)  # 'alerta' | 'limite'
    sent_at: datetime | None = Field(default=None, **server_now_kwargs())
