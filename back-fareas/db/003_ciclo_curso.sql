-- FAREAS - 003_ciclo_curso.sql (2026-10-22)
-- Motivo: cada curso pertenece a un ciclo (I-X) de la malla. El periodo general
-- (course_group.semester_label) no cambia: el ciclo es una dimension del curso
-- dentro del mismo periodo, para poder ver el horario de cada ciclo.
-- Ejecutar manualmente en pgAdmin (Query Tool sobre "fareas") o:
--   psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/003_ciclo_curso.sql
-- Re-ejecutable: no borra datos ni recrea la tabla.

ALTER TABLE course ADD COLUMN IF NOT EXISTS cycle SMALLINT;

UPDATE course SET cycle = 9 WHERE cycle IS NULL;

ALTER TABLE course ALTER COLUMN cycle SET NOT NULL;

ALTER TABLE course DROP CONSTRAINT IF EXISTS chk_course_cycle;
ALTER TABLE course ADD CONSTRAINT chk_course_cycle CHECK (cycle BETWEEN 1 AND 10);
