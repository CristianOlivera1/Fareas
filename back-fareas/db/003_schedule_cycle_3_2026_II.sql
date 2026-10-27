BEGIN;

CREATE TEMP TABLE schedule_cycle_3_seed (
    course_code TEXT NOT NULL,
    group_code TEXT NOT NULL,
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 5),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    room_code TEXT NOT NULL,
    PRIMARY KEY (course_code, group_code, weekday, start_time),
    CHECK (start_time < end_time)
) ON COMMIT DROP;

INSERT INTO schedule_cycle_3_seed
    (course_code, group_code, weekday, start_time, end_time, room_code)
VALUES
    ('AIS31', 'A', 1, '14:00', '16:00', 'LAB 104'),
    ('AIS31', 'A', 4, '14:00', '16:00', 'LAB 103'),
    ('AIS31', 'A', 5, '16:00', '17:00', 'LAB 103'),
    ('AIS32', 'A', 1, '07:00', '09:00', 'LAB 303'),
    ('AIS32', 'A', 3, '07:00', '09:00', 'LAB 305'),
    ('AIS32', 'A', 5, '07:00', '08:00', 'LAB 303'),
    ('AIS32', 'B', 1, '07:00', '09:00', 'LAB 401'),
    ('AIS32', 'B', 3, '07:00', '09:00', 'LAB 303'),
    ('AIS32', 'B', 5, '07:00', '08:00', 'LAB 206'),
    ('AIS33', 'A', 1, '09:00', '11:00', 'LAB 207'),
    ('AIS33', 'A', 3, '09:00', '11:00', 'LAB 207'),
    ('AIS33', 'A', 5, '09:00', '11:00', 'LAB 207'),
    ('AIS33', 'B', 1, '09:00', '11:00', 'LAB 208'),
    ('AIS33', 'B', 3, '09:00', '11:00', 'LAB 208'),
    ('AIS33', 'B', 5, '09:00', '11:00', 'LAB 208'),
    ('AIS34', 'A', 1, '11:00', '13:00', 'LAB 207'),
    ('AIS34', 'A', 3, '11:00', '13:00', 'LAB 207'),
    ('AIS34', 'A', 5, '11:00', '13:00', 'LAB 207'),
    ('AIS34', 'B', 1, '11:00', '13:00', 'LAB 208'),
    ('AIS34', 'B', 3, '11:00', '13:00', 'LAB 208'),
    ('AIS34', 'B', 5, '11:00', '13:00', 'LAB 208'),
    ('AIS35', 'A', 2, '09:00', '11:00', 'LAB 208'),
    ('AIS35', 'A', 4, '09:00', '11:00', 'LAB 208'),
    ('AIS35', 'B', 2, '09:00', '11:00', 'LAB 401'),
    ('AIS35', 'B', 4, '09:00', '11:00', 'LAB 103'),
    ('AGG22', 'A', 2, '07:00', '09:00', 'LAB 103'),
    ('AGG22', 'A', 4, '07:00', '09:00', 'LAB 103'),
    ('AGG22', 'B', 2, '07:00', '09:00', 'LAB 105'),
    ('AGG22', 'B', 4, '07:00', '09:00', 'LAB 105');

DO $$
DECLARE
    missing_rows TEXT;
BEGIN
    SELECT string_agg(
        format('%s %s, día %s %s, aula %s',
            seed.course_code, seed.group_code, seed.weekday, seed.start_time, seed.room_code),
        '; '
    )
    INTO missing_rows
    FROM schedule_cycle_3_seed seed
    LEFT JOIN course c
        ON c.code = seed.course_code
       AND c.cycle = 3
    LEFT JOIN course_group cg
        ON cg.course_id = c.id
       AND cg.group_code = seed.group_code
       AND cg.semester_label = '2026-II'
       AND cg.is_active
    LEFT JOIN room r
        ON r.code = seed.room_code
       AND r.is_active
    WHERE cg.id IS NULL OR r.id IS NULL;

    IF missing_rows IS NOT NULL THEN
        RAISE EXCEPTION 'No se encontraron cursos, grupos activos o aulas: %', missing_rows;
    END IF;
END
$$;

INSERT INTO schedule_block (group_id, room_id, weekday, start_time, end_time)
SELECT cg.id, r.id, seed.weekday, seed.start_time, seed.end_time
FROM schedule_cycle_3_seed seed
JOIN course c
    ON c.code = seed.course_code
   AND c.cycle = 3
JOIN course_group cg
    ON cg.course_id = c.id
   AND cg.group_code = seed.group_code
   AND cg.semester_label = '2026-II'
   AND cg.is_active
JOIN room r
    ON r.code = seed.room_code
   AND r.is_active
ON CONFLICT (group_id, weekday, start_time)
DO UPDATE SET
    end_time = EXCLUDED.end_time,
    room_id = EXCLUDED.room_id;

COMMIT;
