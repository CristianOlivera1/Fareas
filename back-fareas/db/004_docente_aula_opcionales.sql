-- FAREAS - 004_docente_aula_opcionales.sql (2026-10-22)
-- Motivo: algunos horarios llegan incompletos. El docente del grupo y el aula
-- del bloque pueden quedar sin asignar y completarse luego desde el calendario.
-- Las sesiones de asistencia solo se abren cuando ambos datos existen.
-- Ejecutar manualmente en pgAdmin (Query Tool sobre "fareas") o:
--   psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/004_docente_aula_opcionales.sql
-- Re-ejecutable: no borra datos.

ALTER TABLE course_group ALTER COLUMN teacher_id DROP NOT NULL;
ALTER TABLE schedule_block ALTER COLUMN room_id DROP NOT NULL;

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
LEFT JOIN room       r  ON r.id  = sb.room_id
JOIN app_user        st ON st.id = ar.student_id
WHERE s.session_date = CURRENT_DATE
  AND s.status <> 'cancelada';
