-- ============================================================================
-- FAREAS - 007_vistas_reglas.sql (2026-10-11) - requiere 005 y 006 aplicados.
-- Motivo: R7 (DPI con semestre/retiros/justificadas/canceladas) y R5/R6
--         (asistencia de hoy con justificación y sin sesiones canceladas).
-- ============================================================================

-- DPI (R7): solo semestre vigente, sesiones válidas (cerradas, no canceladas,
-- sin needs_review), rango de matrícula del alumno y justificadas aparte.
DROP VIEW IF EXISTS v_student_dpi;
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
           COUNT(*)                                                         AS sessions_held,
           COUNT(*) FILTER (WHERE ar.status = 'falta' AND NOT ar.is_justified) AS absences,
           COUNT(*) FILTER (WHERE ar.status = 'falta' AND ar.is_justified)     AS justified_absences,
           COUNT(*) FILTER (WHERE ar.status = 'tardanza')                      AS lates
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

-- Asistencia de hoy: se AÑADEN columnas al final (CREATE OR REPLACE lo permite
-- solo así) y se excluyen las sesiones canceladas (R5).
CREATE OR REPLACE VIEW v_today_attendance AS
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
