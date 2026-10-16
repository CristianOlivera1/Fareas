-- ============================================================================
-- FAREAS - 005_reglas_negocio.sql  (2026-10-11)
-- Motivo: semestre, cupos, sesiones canceladas/por revisar, justificaciones,
--         retiros, consentimiento facial, alertas DPI sin repetición.
-- Re-ejecutable. Ejecutar ANTES de 006 y 007.
-- ============================================================================

-- 1) Zona horaria de la BD (las vistas usan CURRENT_DATE)
ALTER DATABASE fareas SET timezone TO 'America/Lima';

-- 2) Parámetros (R1, R2, R7, R11) ------------------------------------------
ALTER TABLE app_settings
    ADD COLUMN IF NOT EXISTS semester_start     DATE,
    ADD COLUMN IF NOT EXISTS semester_end       DATE,
    ADD COLUMN IF NOT EXISTS early_open_minutes INTEGER NOT NULL DEFAULT 15,
    ADD COLUMN IF NOT EXISTS rectify_days       INTEGER NOT NULL DEFAULT 7,
    ADD COLUMN IF NOT EXISTS dpi_min_sessions   INTEGER NOT NULL DEFAULT 4;

-- Semestre vigente 2026-II (propuesta confirmada por el usuario 2026-10-11;
-- el admin la ajusta vía PATCH /settings en cualquier momento, RF-34).
-- Niveles DPI: aviso 20 %, inhabilitación al SUPERAR 30 % (R7).
UPDATE app_settings
   SET semester_label    = '2026-II',
       semester_start    = DATE '2026-08-17',
       semester_end      = DATE '2026-12-19',
       dpi_alert_percent = 20.00,
       dpi_limit_percent = 30.00
 WHERE id = 1;

DO $$ BEGIN
  ALTER TABLE app_settings ADD CONSTRAINT chk_dpi_levels CHECK (dpi_alert_percent < dpi_limit_percent);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE app_settings ADD CONSTRAINT chk_semester_dates
    CHECK (semester_start IS NULL OR semester_end IS NULL OR semester_start < semester_end);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE app_settings ADD CONSTRAINT chk_early_open CHECK (early_open_minutes BETWEEN 0 AND 60);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 3) Grupos: semestre + cupo (R1, R8, R9) -----------------------------------
-- La etiqueta se propaga DESPUÉS de fijar el semestre vigente arriba:
-- los grupos demo quedan en '2026-II' y el sistema sigue abriendo sesiones.
ALTER TABLE course_group ADD COLUMN IF NOT EXISTS semester_label VARCHAR(40);
UPDATE course_group
   SET semester_label = (SELECT semester_label FROM app_settings WHERE id = 1)
 WHERE semester_label IS NULL;
ALTER TABLE course_group ALTER COLUMN semester_label SET NOT NULL;
ALTER TABLE course_group ADD COLUMN IF NOT EXISTS capacity INTEGER NOT NULL DEFAULT 40;
DO $$ BEGIN
  ALTER TABLE course_group ADD CONSTRAINT chk_group_capacity CHECK (capacity > 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- Nombre por defecto de PostgreSQL para UNIQUE (course_id, group_code):
ALTER TABLE course_group DROP CONSTRAINT IF EXISTS course_group_course_id_group_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_group_course_code_sem
    ON course_group (course_id, group_code, semester_label);
CREATE INDEX IF NOT EXISTS idx_group_semester ON course_group (semester_label);

-- 4) Sesiones: por revisar / cancelación (R4, R5) ---------------------------
ALTER TABLE attendance_session
    ADD COLUMN IF NOT EXISTS needs_review  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(200),
    ADD COLUMN IF NOT EXISTS cancelled_by  BIGINT REFERENCES app_user(id),
    ADD COLUMN IF NOT EXISTS cancelled_at  TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_session_review
    ON attendance_session (session_date) WHERE needs_review;

-- 5) Registros: falta justificada (R6) --------------------------------------
ALTER TABLE attendance_record
    ADD COLUMN IF NOT EXISTS is_justified     BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS justification_id BIGINT REFERENCES justification(id) ON DELETE SET NULL;
DO $$ BEGIN
  ALTER TABLE attendance_record ADD CONSTRAINT chk_justified_only_falta
      CHECK (is_justified = FALSE OR status = 'falta');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS idx_record_justification
    ON attendance_record (justification_id) WHERE justification_id IS NOT NULL;
-- OJO: ON DELETE SET NULL solo limpia justification_id. El SERVICIO debe poner
-- is_justified = FALSE ANTES de borrar la justificación (ver services/justifications.py).

-- 6) Matrícula: retiro (R8) --------------------------------------------------
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_enrollment_active
    ON enrollment (student_id) WHERE withdrawn_at IS NULL;
-- UNIQUE(student_id, group_id) se mantiene: volver a matricular en el MISMO grupo
-- = poner withdrawn_at = NULL (reactivar), no insertar otra fila.

-- 7) Usuario: consentimiento facial + formatos Perú (R13, R15). NOT VALID =
--    solo filas nuevas/editadas, no rompe los datos demo existentes.
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS face_consent_at TIMESTAMP;
DO $$ BEGIN
  ALTER TABLE app_user ADD CONSTRAINT chk_user_dni_8
      CHECK (dni IS NULL OR dni ~ '^[0-9]{8}$') NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE app_user ADD CONSTRAINT chk_user_whatsapp_pe
      CHECK (whatsapp IS NULL OR whatsapp ~ '^9[0-9]{8}$') NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 8) Aula: aforo informativo (R9) -------------------------------------------
ALTER TABLE room ADD COLUMN IF NOT EXISTS capacity INTEGER;
DO $$ BEGIN
  ALTER TABLE room ADD CONSTRAINT chk_room_capacity CHECK (capacity IS NULL OR capacity > 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 9) Control de alertas DPI: UN correo por nivel (R7) -----------------------
CREATE TABLE IF NOT EXISTS dpi_alert_sent (
    student_id     BIGINT      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    course_id      BIGINT      NOT NULL REFERENCES course(id)   ON DELETE CASCADE,
    semester_label VARCHAR(40) NOT NULL,
    level          VARCHAR(10) NOT NULL CHECK (level IN ('alerta', 'limite')),
    sent_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, course_id, semester_label, level)
);
