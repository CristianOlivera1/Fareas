-- FAREAS — 001_esquema.sql
-- Sistema de control de asistencia con reconocimiento facial

CREATE TYPE user_role         AS ENUM ('admin', 'docente', 'estudiante');          -- RF-01
CREATE TYPE attendance_status AS ENUM ('asistio', 'tardanza', 'falta');            -- RF-23
CREATE TYPE session_status    AS ENUM ('abierta', 'cerrada');                      -- RF-26
CREATE TYPE device_type       AS ENUM ('camara', 'esp32');                         -- RF-05

-- app_settings — parámetros globales del semestre (RF-34, fila única id=1)
CREATE TABLE app_settings (
    id                     INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    semester_label         VARCHAR(40)  NOT NULL,          -- p. ej. '2026-I'
    block_minutes          INTEGER      NOT NULL DEFAULT 120 CHECK (block_minutes > 0),   -- duración del bloque (min)
    late_tolerance_minutes INTEGER      NOT NULL DEFAULT 10 CHECK (late_tolerance_minutes >= 0),  -- RF-23
    face_match_threshold   NUMERIC(4,3) NOT NULL DEFAULT 0.750 CHECK (face_match_threshold BETWEEN 0 AND 1), -- RF-20
    dpi_alert_percent      NUMERIC(5,2) NOT NULL DEFAULT 30.00 CHECK (dpi_alert_percent > 0),  -- RF-24 (límite reglamentario 1/3 ≈ 33.33)
    dpi_limit_percent      NUMERIC(5,2) NOT NULL DEFAULT 33.33,
    attendance_hour_start  TIME         NOT NULL DEFAULT '07:00',
    attendance_hour_end    TIME         NOT NULL DEFAULT '20:00',
    updated_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    CHECK (attendance_hour_start < attendance_hour_end)
);

-- app_user — admin / docentes / estudiantes (RF-01, RF-02, RF-03)
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
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_app_user_role     ON app_user (role);
CREATE INDEX idx_app_user_semester ON app_user (semester) WHERE semester IS NOT NULL;
CREATE INDEX idx_app_user_email_lower ON app_user (LOWER(email));

-- room — aulas de la facultad (RF-05)
CREATE TABLE room (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       VARCHAR(20) NOT NULL UNIQUE,   -- p. ej. 'LAB 304'
    name       VARCHAR(120),
    building   VARCHAR(80),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- device — cámara Hikvision o ESP32 por aula (RF-05, RF-35)
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

-- course / course_group / schedule_block — carga académica (RF-06)
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
    UNIQUE (course_id, group_code)
);
CREATE INDEX idx_group_teacher ON course_group (teacher_id);
CREATE INDEX idx_group_room    ON course_group (room_id);

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

-- enrollment — matrícula estudiante ↔ grupo (RF-03, RF-22)
CREATE TABLE enrollment (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id   BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    group_id     BIGINT NOT NULL REFERENCES course_group(id) ON DELETE CASCADE,
    enrolled_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, group_id)               -- un alumno no se matricula 2 veces en el mismo grupo
);
CREATE INDEX idx_enrollment_group   ON enrollment (group_id);
CREATE INDEX idx_enrollment_student ON enrollment (student_id);

-- face_embedding — enrolamiento biométrico (RF-04, RF-19)
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

-- holiday — feriados y paros (RF-09): no se abren sesiones esos días
CREATE TABLE holiday (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    holiday_date DATE   NOT NULL UNIQUE,
    description VARCHAR(160) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- justification — descansos médicos / faltas justificadas (RF-10)
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

-- attendance_session — apertura de un bloque en una fecha (RF-26)
CREATE TABLE attendance_session (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    block_id    BIGINT        NOT NULL REFERENCES schedule_block(id),
    session_date DATE         NOT NULL,
    status      session_status NOT NULL DEFAULT 'abierta',   -- RF-26: cierre automático
    opened_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
    closed_at   TIMESTAMP,                          -- hora real de cierre (puede ser diferida)
    UNIQUE (block_id, session_date)
);
CREATE INDEX idx_session_lookup ON attendance_session (session_date, status);

-- attendance_record — la marca de asistencia (RF-21, RF-22, RF-23)
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
    UNIQUE (session_id, student_id)                          -- marca única / cooldown (Tabla 2)
);
CREATE INDEX idx_record_student ON attendance_record (student_id);
CREATE INDEX idx_record_session ON attendance_record (session_id);

-- audit_log — bitácora de acciones sensibles (RF-32, solo lectura)
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

-- Trigger updated_at (mantener automáticamente la marca de edición)
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

-- VISTAS de apoyo (dashboard y consultas frecuentes)

-- Asistencia de hoy por curso/grupo (alimenta app-student-list del dashboard)
CREATE VIEW v_today_attendance AS
SELECT
    ar.id                       AS record_id,
    s.session_date              AS att_date,
    st.id                       AS student_id,
    st.code                     AS student_code,
    st.full_name                AS student_name,
    c.id                        AS course_id,
    c.code                      AS course_code,
    c.name                      AS course_name,
    cg.group_code,
    r.code                      AS room_code,
    ar.status,
    ar.marked_at,
    ar.method,
    ar.similarity
FROM attendance_record ar
JOIN attendance_session s ON s.id = ar.session_id
JOIN schedule_block  sb ON sb.id = s.block_id
JOIN course_group    cg ON cg.id = sb.group_id
JOIN course          c  ON c.id  = cg.course_id
JOIN room            r  ON r.id  = cg.room_id
JOIN app_user        st ON st.id = ar.student_id
WHERE s.session_date = CURRENT_DATE;

-- Porcentaje de faltas acumuladas por estudiante/curso (RF-24, alerta DPI).
-- Solo cuentan las sesiones CERRADAS de los grupos propios del alumno.
CREATE VIEW v_student_dpi AS
WITH held AS (
    SELECT e.student_id, cg.course_id, COUNT(s.id) AS sessions_held
    FROM enrollment e
    JOIN course_group cg      ON cg.id = e.group_id
    JOIN schedule_block sb    ON sb.group_id = cg.id
    JOIN attendance_session s ON s.block_id = sb.id AND s.status = 'cerrada'
    GROUP BY e.student_id, cg.course_id
),
absences AS (
    SELECT e.student_id, cg.course_id,
           COUNT(ar.id) FILTER (WHERE ar.status = 'falta') AS absences
    FROM enrollment e
    JOIN course_group cg      ON cg.id = e.group_id
    JOIN schedule_block sb    ON sb.group_id = cg.id
    JOIN attendance_session s ON s.block_id = sb.id AND s.status = 'cerrada'
    LEFT JOIN attendance_record ar ON ar.session_id = s.id AND ar.student_id = e.student_id
    GROUP BY e.student_id, cg.course_id
)
SELECT
    h.student_id,
    h.course_id,
    c.code   AS course_code,
    c.name   AS course_name,
    h.sessions_held,
    COALESCE(a.absences, 0) AS absences,
    CASE WHEN h.sessions_held > 0
         THEN ROUND(COALESCE(a.absences, 0)::numeric * 100 / h.sessions_held, 2)
         ELSE 0 END AS absence_percent
FROM held h
JOIN course c ON c.id = h.course_id
LEFT JOIN absences a ON a.student_id = h.student_id AND a.course_id = h.course_id;
