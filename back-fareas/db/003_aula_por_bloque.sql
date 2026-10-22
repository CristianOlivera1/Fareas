-- ============================================================================
-- FAREAS - 003_aula_por_bloque.sql  (2026-10-16)
-- Motivo: el AULA pasa del grupo al BLOQUE horario (RF-06). El horario real de
--         la facultad dicta el MISMO grupo en aulas distintas según el día
--         (ISA901 en LAB 401 Mar/Jue y en LAB 306 Vie). Aquí course_group.room_id
--         se usa para RELLENAR los bloques; 004 ya lo elimina (correr 003 antes
--         que 004, en este orden).
--         Además la semana lectiva queda en Lunes-Viernes (weekday 1..5) y se
--         alinea un dato del horario demo que impedía usar la API (punto 5).
--
-- Aplicar en una BD que YA existe (re-ejecutable, no recrea ni borra datos):
--     psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/003_aula_por_bloque.sql
--
-- Cuando TODO el equipo lo aplicó, este archivo se BORRA: su contenido ya vive
-- en 001_schema.sql (esquema) y 002_seed.sql (datos demo). Regla completa en
-- README.md >> "Actualizaciones de la base de datos".
-- ============================================================================
BEGIN;

-- 1) Aula por bloque. Se rellena con el aula que tenía el grupo (así ningún
--    bloque queda sin aula) y recién entonces pasa a obligatoria. El UPDATE
--    cubre todas las filas: group_id es NOT NULL y course_group.room_id también.
--    Va en un DO con EXECUTE dinámico porque 004 borra course_group.room_id: así
--    re-ejecutar 003 después de 004 no falla (ya no hay nada que rellenar).
ALTER TABLE schedule_block ADD COLUMN IF NOT EXISTS room_id BIGINT;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'course_group'
          AND column_name = 'room_id'
    ) THEN
        EXECUTE $sql$
            UPDATE schedule_block sb
               SET room_id = g.room_id
              FROM course_group g
             WHERE g.id = sb.group_id
               AND sb.room_id IS NULL
        $sql$;
    END IF;
END $$;
ALTER TABLE schedule_block ALTER COLUMN room_id SET NOT NULL;

-- 2) FK + índice por aula: lo usan la validación de choques (RF-06), el motor de
--    asistencia (qué clase ocurre en cada aula) y las vistas de hoy.
ALTER TABLE schedule_block DROP CONSTRAINT IF EXISTS schedule_block_room_id_fkey;
ALTER TABLE schedule_block ADD CONSTRAINT schedule_block_room_id_fkey
    FOREIGN KEY (room_id) REFERENCES room(id);
CREATE INDEX IF NOT EXISTS idx_block_room ON schedule_block (room_id);

-- 3) Semana lectiva Lunes-Viernes. El CHECK entra NOT VALID (igual que
--    chk_user_dni_8): controla las altas y ediciones nuevas SIN revalidar los
--    bloques que ya existían, para que la migración no falle en ninguna BD.
ALTER TABLE schedule_block DROP CONSTRAINT IF EXISTS schedule_block_weekday_check;
ALTER TABLE schedule_block ADD CONSTRAINT schedule_block_weekday_check
    CHECK (weekday BETWEEN 1 AND 5) NOT VALID;
DO $$
DECLARE n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM schedule_block WHERE weekday NOT BETWEEN 1 AND 5;
    IF n > 0 THEN
        RAISE NOTICE 'OJO: % bloque(s) con weekday 6/7 quedaron sin revalidar (ya no se pueden crear). Revisalos con: SELECT * FROM schedule_block WHERE weekday NOT BETWEEN 1 AND 5;', n;
    END IF;
END $$;

-- 4) La vista del día debe leer el aula DEL BLOQUE (antes leía la del grupo).
--    Mismas columnas y mismo orden: CREATE OR REPLACE es válido.
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
JOIN room            r  ON r.id  = sb.room_id
JOIN app_user        st ON st.id = ar.student_id
WHERE s.session_date = CURRENT_DATE
  AND s.status <> 'cancelada';

-- 5) Alineación del horario DEMO (solo si sigue igual que lo sembró
--    002_seed.sql): ISA901 grupo A tenía Vie 09:00-11:00, que se cruza con
--    ISA905 grupo A para los 6 alumnos matriculados en ambos cursos. Como
--    R8c/R9 rechaza CUALQUIER alta en esos grupos, el seed lo mueve a
--    Vie 07:00-09:00 en LAB 306 (como el horario de la facultad). Si ese bloque
--    ya lo cambiaste a mano, este UPDATE no lo toca.
UPDATE schedule_block sb
   SET start_time = TIME '07:00', end_time = TIME '09:00', room_id = r.id
  FROM course_group g, course c, room r
 WHERE g.id = sb.group_id
   AND c.id = g.course_id
   AND r.code = 'LAB 306'
   AND c.code = 'ISA901' AND g.group_code = 'A'
   AND sb.weekday = 5
   AND sb.start_time = TIME '09:00' AND sb.end_time = TIME '11:00';

COMMIT;
