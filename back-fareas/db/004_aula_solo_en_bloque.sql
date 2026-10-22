BEGIN;

-- 1) El índice de la columna muere con ella, pero se nombra para que el script
--    sea idempotente en BD donde el nombre difiera.
DROP INDEX IF EXISTS idx_group_room;

-- 2) Fuera la columna. CASCADE no hace falta: nada más la referencia (la vista
--    del día lee schedule_block.room_id desde 003). IF EXISTS lo hace
--    re-ejecutable.
ALTER TABLE course_group DROP COLUMN IF EXISTS room_id;

COMMIT;
