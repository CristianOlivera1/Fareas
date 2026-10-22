-- ============================================================================
-- FAREAS - 001_schema.sql  |  ESQUEMA COMPLETO Y VIGENTE
-- Sistema de control de asistencia con reconocimiento facial (RF-01 … RF-35)
--
-- ESTE ARCHIVO ES LA ÚNICA FUENTE DE VERDAD DE LA ESTRUCTURA. Siempre refleja
-- la BD de desarrollo tal cual está. Puesta en marcha desde cero:
--
--     psql -U postgres -d fareas -f db/001_schema.sql
--     psql -U postgres -d fareas -f db/002_seed.sql
--
-- Reglas de mantenimiento de la BD (detalle en README.md >> "Actualizaciones
-- de la base de datos"): si un cambio toca el esquema o los datos demo, se deja
-- este archivo (y 002_seed.sql si aplica) actualizado EN EL MISMO COMMIT que el
-- ALTER nuevo, y se BORRA el ALTER ya aplicado por todo el equipo. Resultado:
-- un desarrollador nuevo -o una BD vieja- se pone al día con estos 2 scripts.
--
-- Origen del DDL: `pg_dump --schema-only --no-owner --no-acl fareas`, que se
-- regenera tras aplicar cualquier cambio en la BD de desarrollo.
-- ============================================================================

-- Zona horaria de la BD: las vistas usan CURRENT_DATE y las sesiones se abren
-- por fecha local de Abancay (America/Lima, sin DST).
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone TO ''America/Lima''', current_database());
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Sin permisos para fijar la zona horaria: fija America/Lima en el servidor.';
END $$;

-- TIPOS ENUMERADOS -----------------------------------------------------------
CREATE TYPE user_role         AS ENUM ('admin', 'docente', 'estudiante');          -- RF-01
CREATE TYPE attendance_status AS ENUM ('asistio', 'tardanza', 'falta');            -- RF-23
CREATE TYPE session_status    AS ENUM ('abierta', 'cerrada', 'cancelada');          -- RF-26, R5
CREATE TYPE device_type       AS ENUM ('camara', 'esp32');                         -- RF-05

-- TABLAS ---------------------------------------------------------------------

-- app_settings - parámetros globales del semestre (RF-34, fila única id=1).
-- Los valores vigentes (semestre, niveles DPI, umbral facial) los fija
-- 002_seed.sql: el admin los edita luego con PATCH /settings.
CREATE TABLE app_settings (
    id                     INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    semester_label         VARCHAR(40)  NOT NULL,          -- p. ej. '2026-II'
    block_minutes          INTEGER      NOT NULL DEFAULT 120 CHECK (block_minutes > 0),
    late_tolerance_minutes INTEGER      NOT NULL DEFAULT 10 CHECK (late_tolerance_minutes >= 0),  -- RF-23
    face_match_threshold   NUMERIC(4,3) NOT NULL DEFAULT 0.750 CHECK (face_match_threshold BETWEEN 0 AND 1),  -- RF-20
    dpi_alert_percent      NUMERIC(5,2) NOT NULL DEFAULT 30.00 CHECK (dpi_alert_percent > 0),     -- RF-24
    dpi_limit_percent      NUMERIC(5,2) NOT NULL DEFAULT 33.33,
    attendance_hour_start  TIME         NOT NULL DEFAULT '07:00',
    attendance_hour_end    TIME         NOT NULL DEFAULT '20:00',
    updated_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    semester_start         DATE,                            -- R1: fechas del semestre vigente
    semester_end           DATE,
    early_open_minutes     INTEGER      NOT NULL DEFAULT 15,   -- R3: apertura anticipada de la sesión
    rectify_days           INTEGER      NOT NULL DEFAULT 7,    -- R11: plazo del docente para rectificar
    dpi_min_sessions       INTEGER      NOT NULL DEFAULT 4,    -- R7: correo DPI solo con historial suficiente
    CONSTRAINT chk_dpi_levels     CHECK (dpi_alert_percent < dpi_limit_percent),
    CONSTRAINT chk_semester_dates CHECK (semester_start IS NULL OR semester_end IS NULL
                                         OR semester_start < semester_end),
    CONSTRAINT chk_early_open     CHECK (early_open_minutes BETWEEN 0 AND 60),
    CHECK (attendance_hour_start < attendance_hour_end)
);

-- app_user - admin / docentes / estudiantes (RF-01, RF-02, RF-03)
CREATE TABLE app_user (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role                 user_role    NOT NULL,
    dni                  VARCHAR(12)  UNIQUE,             -- RF-02/RF-03
    code                 VARCHAR(20)  UNIQUE,             -- código de matrícula (estudiante)
    email                VARCHAR(160) NOT NULL UNIQUE,    -- correo institucional @unamba.edu.pe (RF-08/RF-12)
    full_name            VARCHAR(160) NOT NULL,
    whatsapp             VARCHAR(20),                     -- RF-02/RF-03
    password_hash        VARCHAR(128) NOT NULL,           -- argon2id (97 chars)
    must_change_password BOOLEAN      NOT NULL DEFAULT TRUE,   -- RF-11: clave temporal
    semester             SMALLINT,                        -- ciclo del estudiante
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    face_consent_at      TIMESTAMP,                       -- R13 (Ley 29733): consentimiento biométrico
    token_version        INTEGER      NOT NULL DEFAULT 0  -- invalida JWT al cambiar contraseña
);
-- R15: formatos de Perú. NOT VALID a propósito: no revalida los datos que ya
-- existían (solo controla altas y ediciones nuevas).
ALTER TABLE app_user ADD CONSTRAINT chk_user_dni_8
    CHECK (dni IS NULL OR dni ~ '^[0-9]{8}$') NOT VALID;
ALTER TABLE app_user ADD CONSTRAINT chk_user_whatsapp_pe
    CHECK (whatsapp IS NULL OR whatsapp ~ '^9[0-9]{8}$') NOT VALID;
CREATE INDEX idx_app_user_role     ON app_user (role);
CREATE INDEX idx_app_user_semester ON app_user (semester) WHERE semester IS NOT NULL;
CREATE INDEX idx_app_user_email_lower ON app_user (LOWER(email));

-- room - aulas de la facultad (RF-05)
CREATE TABLE room (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       VARCHAR(20) NOT NULL UNIQUE,   -- p. ej. 'LAB 304'
    name       VARCHAR(120),
    building   VARCHAR(80),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    capacity   INTEGER,                       -- R9: aforo informativo (NULL = no declarado)
    CONSTRAINT chk_room_capacity CHECK (capacity IS NULL OR capacity > 0)
);

-- device - cámara Hikvision o ESP32 por aula (RF-05, RF-35)
-- NOTA: el backend identifica el aula por la identidad del dispositivo
-- conectado (device_key), no por su IP dinámica.
CREATE TABLE device (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id       BIGINT      NOT NULL REFERENCES room(id),
    device_type   device_type NOT NULL,
    device_key    VARCHAR(64) NOT NULL UNIQUE,   -- identificador lógico: 'esp32-lab305' / 'cam-lab305'
    name          VARCHAR(80),
    ip_address    VARCHAR(45),                   -- informativo (DHCP)
    mac_address   VARCHAR(17),                   -- RF-05
    rtsp_url      VARCHAR(255),                  -- solo cámaras: rtsp://user:pass@ip:554/...
    is_online     BOOLEAN     NOT NULL DEFAULT FALSE,  -- RF-35
    last_heartbeat TIMESTAMP,                         -- RF-33
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP   NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_device_room ON device (room_id);

-- course / course_group / schedule_block - carga académica (RF-06)
CREATE TABLE course (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       VARCHAR(20) NOT NULL UNIQUE,   -- p. ej. 'ISA903'
    name       VARCHAR(160) NOT NULL,         -- 'Inteligencia Artificial I'
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE course_group (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id  BIGINT      NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    group_code VARCHAR(5)  NOT NULL,          -- 'A' | 'B' | 'C' ...
    teacher_id BIGINT      NOT NULL REFERENCES app_user(id),
    room_id    BIGINT      NOT NULL REFERENCES room(id),
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP   NOT NULL DEFAULT NOW(),
    semester_label VARCHAR(40) NOT NULL,      -- R1: cada grupo vive en UN semestre
    capacity       INTEGER NOT NULL DEFAULT 40,
    CONSTRAINT chk_group_capacity CHECK (capacity > 0)
);
-- El grupo se repite por semestre: 'ISA903-A' puede existir en 2026-I y 2026-II.
CREATE UNIQUE INDEX uq_group_course_code_sem ON course_group (course_id, group_code, semester_label);
CREATE INDEX idx_group_semester ON course_group (semester_label);
CREATE INDEX idx_group_teacher  ON course_group (teacher_id);
CREATE INDEX idx_group_room     ON course_group (room_id);

CREATE TABLE schedule_block (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id   BIGINT NOT NULL REFERENCES course_group(id) ON DELETE CASCADE,
    weekday    SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    start_time TIME     NOT NULL,
    end_time   TIME     NOT NULL,
    CHECK (start_time < end_time)
);
-- Evita duplicar el mismo bloque de un grupo; la validación de SOLAPAMIENTO
-- (misma aula o mismo docente en horarios que se cruzan, RF-06) la aplica la
-- API al crear bloques, porque sí son válidos los bloques simultáneos en
-- aulas y docentes distintos (grupos paralelos, Tabla 2 del documento).
CREATE UNIQUE INDEX uq_block_group_time ON schedule_block (group_id, weekday, start_time);
CREATE INDEX idx_block_lookup ON schedule_block (weekday, start_time);

-- enrollment - matrícula estudiante ↔ grupo (RF-03, RF-22)
CREATE TABLE enrollment (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id   BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    group_id     BIGINT NOT NULL REFERENCES course_group(id) ON DELETE CASCADE,
    enrolled_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    withdrawn_at TIMESTAMP,                        -- R8: retiro (NULL = activo)
    UNIQUE (student_id, group_id)                  -- un alumno no se matricula 2 veces en el mismo grupo
);
-- R8: volver al MISMO grupo = reactivar (withdrawn_at = NULL), no insertar otra fila.
CREATE INDEX idx_enrollment_active  ON enrollment (student_id) WHERE withdrawn_at IS NULL;
CREATE INDEX idx_enrollment_group   ON enrollment (group_id);
CREATE INDEX idx_enrollment_student ON enrollment (student_id);

-- face_embedding - enrolamiento biométrico (RF-04, RF-19)
-- vector: embedding promedio de 3-5 fotos, 512 dimensiones (ArcFace).
CREATE TABLE face_embedding (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id  BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    vector      REAL[512]   NOT NULL,           -- búsqueda de coseno en Python (sin pgvector)
    photo_url   VARCHAR(500),                   -- storage/ en dev, Cloudflare R2 en prod
    source      VARCHAR(20) NOT NULL DEFAULT 'upload' CHECK (source IN ('upload', 'promedio')),
    is_current  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);
-- Solo el embedding vigente participa de la búsqueda.
CREATE INDEX idx_face_current ON face_embedding (student_id) WHERE is_current;
CREATE INDEX idx_face_student ON face_embedding (student_id);

-- holiday - feriados y paros (RF-09, R12): no se abren sesiones esos días
CREATE TABLE holiday (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    holiday_date DATE   NOT NULL UNIQUE,
    description VARCHAR(160) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- justification - descansos médicos / faltas justificadas (RF-10, R6)
CREATE TABLE justification (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id  BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    course_id   BIGINT      REFERENCES course(id),      -- NULL = aplica a todos los cursos
    start_date  DATE        NOT NULL,
    end_date    DATE        NOT NULL,
    reason      VARCHAR(400) NOT NULL,
    document_url VARCHAR(500),                          -- escaneo del descanso médico
    created_by  BIGINT      NOT NULL REFERENCES app_user(id),
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    CHECK (start_date <= end_date)
);
CREATE INDEX idx_justification_student ON justification (student_id, start_date, end_date);

-- attendance_session - apertura de un bloque en una fecha (RF-26, R3/R4/R5)
CREATE TABLE attendance_session (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    block_id    BIGINT        NOT NULL REFERENCES schedule_block(id),
    session_date DATE         NOT NULL,
    status      session_status NOT NULL DEFAULT 'abierta',   -- RF-26: cierre automático
    opened_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
    closed_at   TIMESTAMP,                          -- hora real de cierre (puede ser diferida)
    needs_review  BOOLEAN     NOT NULL DEFAULT FALSE,   -- R4: cerrada sin marcas (¿cámara caída?)
    cancel_reason VARCHAR(200),                         -- R5: feriado olvidado / paro
    cancelled_by  BIGINT REFERENCES app_user(id),
    cancelled_at  TIMESTAMP,
    UNIQUE (block_id, session_date)
);
CREATE INDEX idx_session_lookup ON attendance_session (session_date, status);
CREATE INDEX idx_session_review ON attendance_session (session_date) WHERE needs_review;

-- attendance_record - la marca de asistencia (RF-21, RF-22, RF-23, R6)
CREATE TABLE attendance_record (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id       BIGINT      NOT NULL REFERENCES attendance_session(id) ON DELETE CASCADE,
    student_id       BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    status           attendance_status NOT NULL,               -- RF-23
    marked_at        TIMESTAMP,                              -- RF-21: hora de la marca (NULL = falta por cierre RF-26)
    method           VARCHAR(10) NOT NULL DEFAULT 'facial' CHECK (method IN ('facial', 'manual')),
    similarity       NUMERIC(5,4),                           -- similitud coseno de la identificación (RF-20)
    corrected_by     BIGINT REFERENCES app_user(id),         -- RF-15: rectificación docente
    corrected_at     TIMESTAMP,
    correct_reason   VARCHAR(400),                           -- justificación presencial obligatoria
    created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    is_justified     BOOLEAN NOT NULL DEFAULT FALSE,          -- R6: falta justificada (FJ)
    justification_id BIGINT REFERENCES justification(id) ON DELETE SET NULL,
    UNIQUE (session_id, student_id),                          -- marca única / cooldown (Tabla 2)
    CONSTRAINT chk_justified_only_falta CHECK (is_justified = FALSE OR status = 'falta')
);
-- OJO: ON DELETE SET NULL solo limpia justification_id. El SERVICIO debe poner
-- is_justified = FALSE ANTES de borrar la justificación (services/justifications.py).
CREATE INDEX idx_record_student ON attendance_record (student_id);
CREATE INDEX idx_record_session ON attendance_record (session_id);
CREATE INDEX idx_record_justification ON attendance_record (justification_id)
    WHERE justification_id IS NOT NULL;

-- audit_log - bitácora de acciones sensibles (RF-32, solo lectura)
CREATE TABLE audit_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id     BIGINT       REFERENCES app_user(id),      -- NULL = proceso del sistema (scheduler)
    action       VARCHAR(40)  NOT NULL,       -- 'rectificacion' | 'credenciales_reenviadas' | 'justificacion' | 'sistema' ...
    entity       VARCHAR(40)  NOT NULL,       -- 'attendance_record' | 'app_user' | ...
    entity_id    BIGINT,
    old_value    JSONB,                       -- estado anterior (RF-32)
    new_value    JSONB,
    ip_address   VARCHAR(45),
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_entity ON audit_log (entity, entity_id);
CREATE INDEX idx_audit_actor  ON audit_log (actor_id);
CREATE INDEX idx_audit_time   ON audit_log (created_at);

-- dpi_alert_sent - control de alertas DPI (R7): UN correo por nivel
-- (alerta/limite) por alumno-curso-semestre. El servicio inserta primero
-- (ON CONFLICT DO NOTHING): si no insertó, ya se envió y no se repite.
CREATE TABLE dpi_alert_sent (
    student_id     BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    course_id      BIGINT      NOT NULL REFERENCES course(id)   ON DELETE CASCADE,
    semester_label VARCHAR(40) NOT NULL,
    level          VARCHAR(10) NOT NULL CHECK (level IN ('alerta', 'limite')),
    sent_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, course_id, semester_label, level)
);

-- TRIGGERS -------------------------------------------------------------------

-- Mantiene updated_at automáticamente en cada UPDATE.
CREATE OR REPLACE FUNCTION fn_set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_user_updated_at
    BEFORE UPDATE ON app_user
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TRIGGER trg_settings_updated_at
    BEFORE UPDATE ON app_settings
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- VISTAS de apoyo (dashboard y consultas frecuentes) --------------------------

-- Asistencia de hoy por curso/grupo (alimenta app-student-list del dashboard).
-- Excluye las sesiones canceladas (R5) y expone la justificación (R6).
CREATE VIEW v_today_attendance AS
SELECT
    ar.id            AS record_id,
    s.session_date   AS att_date,
    st.id            AS student_id,
    st.code          AS student_code,
    st.full_name     AS student_name,
    c.id             AS course_id,
    c.code           AS course_code,
    c.name           AS course_name,
    cg.group_code,
    r.code           AS room_code,
    ar.status,
    ar.marked_at,
    ar.method,
    ar.similarity,
    ar.is_justified,
    s.id             AS session_id,
    sb.start_time,
    sb.end_time,
    ar.correct_reason,
    cg.teacher_id
FROM attendance_record ar
JOIN attendance_session s ON s.id = ar.session_id
JOIN schedule_block  sb ON sb.id = s.block_id
JOIN course_group    cg ON cg.id = sb.group_id
JOIN course          c  ON c.id  = cg.course_id
JOIN room            r  ON r.id  = cg.room_id
JOIN app_user        st ON st.id = ar.student_id
WHERE s.session_date = CURRENT_DATE
  AND s.status <> 'cancelada';

-- DPI (R7): solo semestre vigente, sesiones VÁLIDAS (cerradas, no canceladas,
-- sin needs_review), rango de matrícula del alumno (alta → retiro) y las
-- justificadas contadas aparte (no suman al porcentaje de ausentismo).
CREATE VIEW v_student_dpi AS
WITH cfg AS (
    SELECT semester_label FROM app_settings WHERE id = 1
),
valid AS (
    SELECT e.student_id, cg.course_id, cfg.semester_label, s.id AS session_id
    FROM enrollment e
    JOIN course_group cg      ON cg.id = e.group_id
    JOIN cfg                  ON cg.semester_label = cfg.semester_label
    JOIN schedule_block sb    ON sb.group_id = cg.id
    JOIN attendance_session s ON s.block_id = sb.id
                             AND s.status = 'cerrada'
                             AND s.needs_review = FALSE
                             AND s.session_date >= e.enrolled_at::date
                             AND (e.withdrawn_at IS NULL OR s.session_date <= e.withdrawn_at::date)
),
agg AS (
    SELECT v.student_id, v.course_id, v.semester_label,
           COUNT(*)                                                            AS sessions_held,
           COUNT(*) FILTER (WHERE ar.status = 'falta' AND NOT ar.is_justified)  AS absences,
           COUNT(*) FILTER (WHERE ar.status = 'falta' AND ar.is_justified)      AS justified_absences,
           COUNT(*) FILTER (WHERE ar.status = 'tardanza')                       AS lates
    FROM valid v
    LEFT JOIN attendance_record ar
           ON ar.session_id = v.session_id AND ar.student_id = v.student_id
    GROUP BY v.student_id, v.course_id, v.semester_label
)
SELECT a.student_id,
       a.course_id,
       c.code AS course_code,
       c.name AS course_name,
       a.sessions_held,
       a.absences,
       CASE WHEN a.sessions_held > 0
            THEN ROUND(a.absences::numeric * 100 / a.sessions_held, 2)
            ELSE 0 END AS absence_percent,
       a.justified_absences,
       a.lates,
       a.semester_label
FROM agg a
JOIN course c ON c.id = a.course_id;
