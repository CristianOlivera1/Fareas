DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone TO ''America/Lima''', current_database());
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'Sin permisos para fijar la zona horaria: fija America/Lima en el servidor.';
END $$;

CREATE TYPE user_role         AS ENUM ('admin', 'docente', 'estudiante');
CREATE TYPE attendance_status AS ENUM ('asistio', 'tardanza', 'falta');
CREATE TYPE session_status    AS ENUM ('abierta', 'cerrada', 'cancelada');
CREATE TYPE device_type       AS ENUM ('camara', 'esp32');

CREATE TABLE app_settings (
    id                     INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    semester_label         VARCHAR(40)  NOT NULL,
    block_minutes          INTEGER      NOT NULL DEFAULT 120 CHECK (block_minutes > 0),
    late_tolerance_minutes INTEGER      NOT NULL DEFAULT 10 CHECK (late_tolerance_minutes >= 0),
    face_match_threshold   NUMERIC(4,3) NOT NULL DEFAULT 0.750 CHECK (face_match_threshold BETWEEN 0 AND 1),
    dpi_alert_percent      NUMERIC(5,2) NOT NULL DEFAULT 30.00 CHECK (dpi_alert_percent > 0),
    dpi_limit_percent      NUMERIC(5,2) NOT NULL DEFAULT 33.33,
    attendance_hour_start  TIME         NOT NULL DEFAULT '07:00',
    attendance_hour_end    TIME         NOT NULL DEFAULT '20:00',
    updated_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    semester_start         DATE,
    semester_end           DATE,
    early_open_minutes     INTEGER      NOT NULL DEFAULT 15,
    rectify_days           INTEGER      NOT NULL DEFAULT 7,
    dpi_min_sessions       INTEGER      NOT NULL DEFAULT 4,
    CONSTRAINT chk_dpi_levels     CHECK (dpi_alert_percent < dpi_limit_percent),
    CONSTRAINT chk_semester_dates CHECK (semester_start IS NULL OR semester_end IS NULL
                                         OR semester_start < semester_end),
    CONSTRAINT chk_early_open     CHECK (early_open_minutes BETWEEN 0 AND 60),
    CHECK (attendance_hour_start < attendance_hour_end)
);

CREATE TABLE app_user (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role                 user_role    NOT NULL,
    dni                  VARCHAR(12)  UNIQUE,
    code                 VARCHAR(20)  UNIQUE,
    email                VARCHAR(160) NOT NULL UNIQUE,
    full_name            VARCHAR(160) NOT NULL,
    whatsapp             VARCHAR(20),
    password_hash        VARCHAR(128) NOT NULL,
    must_change_password BOOLEAN      NOT NULL DEFAULT TRUE,
    semester             SMALLINT,
    is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    face_consent_at      TIMESTAMP,
    token_version        INTEGER      NOT NULL DEFAULT 0
);
ALTER TABLE app_user ADD CONSTRAINT chk_user_dni_8
    CHECK (dni IS NULL OR dni ~ '^[0-9]{8}$') NOT VALID;
ALTER TABLE app_user ADD CONSTRAINT chk_user_whatsapp_pe
    CHECK (whatsapp IS NULL OR whatsapp ~ '^9[0-9]{8}$') NOT VALID;
CREATE INDEX idx_app_user_role     ON app_user (role);
CREATE INDEX idx_app_user_semester ON app_user (semester) WHERE semester IS NOT NULL;
CREATE INDEX idx_app_user_email_lower ON app_user (LOWER(email));

CREATE TABLE room (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       VARCHAR(20) NOT NULL UNIQUE,
    name       VARCHAR(120),
    building   VARCHAR(80),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    capacity   INTEGER,
    CONSTRAINT chk_room_capacity CHECK (capacity IS NULL OR capacity > 0)
);

CREATE TABLE device (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id       BIGINT      NOT NULL REFERENCES room(id),
    device_type   device_type NOT NULL,
    device_key    VARCHAR(64) NOT NULL UNIQUE,
    name          VARCHAR(80),
    ip_address    VARCHAR(45),
    mac_address   VARCHAR(17),
    rtsp_url      VARCHAR(255),
    is_online     BOOLEAN     NOT NULL DEFAULT FALSE,
    last_heartbeat TIMESTAMP,
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP   NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_device_room ON device (room_id);

CREATE TABLE course (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       VARCHAR(20) NOT NULL UNIQUE,
    name       VARCHAR(160) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cycle      SMALLINT NOT NULL,
    CONSTRAINT chk_course_cycle CHECK (cycle BETWEEN 1 AND 10)
);

CREATE TABLE course_group (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id  BIGINT      NOT NULL REFERENCES course(id) ON DELETE CASCADE,
    group_code VARCHAR(5)  NOT NULL,
    teacher_id BIGINT      NOT NULL REFERENCES app_user(id),
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP   NOT NULL DEFAULT NOW(),
    semester_label VARCHAR(40) NOT NULL,
    capacity       INTEGER NOT NULL DEFAULT 40,
    CONSTRAINT chk_group_capacity CHECK (capacity > 0)
);
CREATE UNIQUE INDEX uq_group_course_code_sem ON course_group (course_id, group_code, semester_label);
CREATE INDEX idx_group_semester ON course_group (semester_label);
CREATE INDEX idx_group_teacher  ON course_group (teacher_id);

CREATE TABLE schedule_block (
    id         BIGINT   GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id   BIGINT   NOT NULL REFERENCES course_group(id) ON DELETE CASCADE,
    weekday    SMALLINT NOT NULL,
    start_time TIME     NOT NULL,
    end_time   TIME     NOT NULL,
    room_id    BIGINT   NOT NULL REFERENCES room(id),
    CHECK (start_time < end_time)
);
ALTER TABLE schedule_block ADD CONSTRAINT schedule_block_weekday_check
    CHECK (weekday BETWEEN 1 AND 5) NOT VALID;
CREATE UNIQUE INDEX uq_block_group_time ON schedule_block (group_id, weekday, start_time);
CREATE INDEX idx_block_lookup ON schedule_block (weekday, start_time);
CREATE INDEX idx_block_room   ON schedule_block (room_id);

CREATE TABLE enrollment (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id   BIGINT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    group_id     BIGINT NOT NULL REFERENCES course_group(id) ON DELETE CASCADE,
    enrolled_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    withdrawn_at TIMESTAMP,
    UNIQUE (student_id, group_id)
);
CREATE INDEX idx_enrollment_active  ON enrollment (student_id) WHERE withdrawn_at IS NULL;
CREATE INDEX idx_enrollment_group   ON enrollment (group_id);
CREATE INDEX idx_enrollment_student ON enrollment (student_id);

CREATE TABLE face_embedding (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id  BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    vector      REAL[512]   NOT NULL,
    photo_url   VARCHAR(500),
    source      VARCHAR(20) NOT NULL DEFAULT 'upload' CHECK (source IN ('upload', 'promedio')),
    is_current  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_face_current ON face_embedding (student_id) WHERE is_current;
CREATE INDEX idx_face_student ON face_embedding (student_id);

CREATE TABLE holiday (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    holiday_date DATE   NOT NULL UNIQUE,
    description VARCHAR(160) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE justification (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id  BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    course_id   BIGINT      REFERENCES course(id),
    start_date  DATE        NOT NULL,
    end_date    DATE        NOT NULL,
    reason      VARCHAR(400) NOT NULL,
    document_url VARCHAR(500),
    created_by  BIGINT      NOT NULL REFERENCES app_user(id),
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    CHECK (start_date <= end_date)
);
CREATE INDEX idx_justification_student ON justification (student_id, start_date, end_date);

CREATE TABLE attendance_session (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    block_id    BIGINT        NOT NULL REFERENCES schedule_block(id),
    session_date DATE         NOT NULL,
    status      session_status NOT NULL DEFAULT 'abierta',
    opened_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
    closed_at   TIMESTAMP,
    needs_review  BOOLEAN     NOT NULL DEFAULT FALSE,
    cancel_reason VARCHAR(200),
    cancelled_by  BIGINT REFERENCES app_user(id),
    cancelled_at  TIMESTAMP,
    UNIQUE (block_id, session_date)
);
CREATE INDEX idx_session_lookup ON attendance_session (session_date, status);
CREATE INDEX idx_session_review ON attendance_session (session_date) WHERE needs_review;

CREATE TABLE attendance_record (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id       BIGINT      NOT NULL REFERENCES attendance_session(id) ON DELETE CASCADE,
    student_id       BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    status           attendance_status NOT NULL,
    marked_at        TIMESTAMP,
    method           VARCHAR(10) NOT NULL DEFAULT 'facial' CHECK (method IN ('facial', 'manual')),
    similarity       NUMERIC(5,4),
    corrected_by     BIGINT REFERENCES app_user(id),
    corrected_at     TIMESTAMP,
    correct_reason   VARCHAR(400),
    created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    is_justified     BOOLEAN NOT NULL DEFAULT FALSE,
    justification_id BIGINT REFERENCES justification(id) ON DELETE SET NULL,
    UNIQUE (session_id, student_id),
    CONSTRAINT chk_justified_only_falta CHECK (is_justified = FALSE OR status = 'falta')
);
CREATE INDEX idx_record_student ON attendance_record (student_id);
CREATE INDEX idx_record_session ON attendance_record (session_id);
CREATE INDEX idx_record_justification ON attendance_record (justification_id)
    WHERE justification_id IS NOT NULL;

CREATE TABLE audit_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id     BIGINT       REFERENCES app_user(id),
    action       VARCHAR(40)  NOT NULL,
    entity       VARCHAR(40)  NOT NULL,
    entity_id    BIGINT,
    old_value    JSONB,
    new_value    JSONB,
    ip_address   VARCHAR(45),
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_entity ON audit_log (entity, entity_id);
CREATE INDEX idx_audit_actor  ON audit_log (actor_id);
CREATE INDEX idx_audit_time   ON audit_log (created_at);

CREATE TABLE dpi_alert_sent (
    student_id     BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    course_id      BIGINT      NOT NULL REFERENCES course(id)   ON DELETE CASCADE,
    semester_label VARCHAR(40) NOT NULL,
    level          VARCHAR(10) NOT NULL CHECK (level IN ('alerta', 'limite')),
    sent_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, course_id, semester_label, level)
);

CREATE TABLE refresh_token (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    family_id       UUID        NOT NULL,
    token_hash      VARCHAR(64) NOT NULL UNIQUE,
    token_version   INTEGER     NOT NULL DEFAULT 0,
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revoked_reason  VARCHAR(40),
    replaced_by_id  BIGINT REFERENCES refresh_token(id) ON DELETE SET NULL,
    user_agent      VARCHAR(300),
    ip_address      VARCHAR(45),
    CONSTRAINT chk_refresh_expiry CHECK (expires_at > issued_at)
);
CREATE INDEX idx_refresh_user   ON refresh_token (user_id);
CREATE INDEX idx_refresh_family ON refresh_token (family_id);
CREATE INDEX idx_refresh_active ON refresh_token (user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_expiry ON refresh_token (expires_at) WHERE revoked_at IS NULL;

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
JOIN room            r  ON r.id  = sb.room_id
JOIN app_user        st ON st.id = ar.student_id
WHERE s.session_date = CURRENT_DATE
  AND s.status <> 'cancelada';

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
