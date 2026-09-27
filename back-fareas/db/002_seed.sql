-- FAREAS - 002_seed.sql
-- Usuarios demo (contraseña de TODOS: 12345678 - argon2id):
--   admin / docente / estudiante
BEGIN;

-- app_settings (RF-34) - fila única
INSERT INTO app_settings (id, semester_label)
VALUES (1, '2026-I')
ON CONFLICT (id) DO NOTHING;

-- Usuarios demo
INSERT INTO app_user (role, dni, code, email, full_name, whatsapp, password_hash, must_change_password, semester)
VALUES
  ('admin',      '71234567', NULL,       'admin@unamba.edu.pe',      'Admin Fareas',              '900000001', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),
  ('docente',    '71234568', 'DOC-001',  'aquino.mario@unamba.edu.pe','Aquino Cruz, Mario (Mag.)', '900000002', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),
  ('docente',    '71234569', 'DOC-002',  'cari.francisco@unamba.edu.pe','Cari Incahuanaco, Francisco (Mag.)', '900000003', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),
  ('estudiante', '71234570', '221181',   'raul.montesinos@unamba.edu.pe', 'Raul Montesinos Valdivia', '900000004', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9),
  ('estudiante', '71234571', '231204',   'razib.rahman@unamba.edu.pe',   'Razib Rahman Ttito',       '900000005', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9),
  ('estudiante', '71234572', '221105',   'lucia.fernandez@unamba.edu.pe','Lucía Fernández Quispe',   '900000006', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9),
  ('estudiante', '71234573', '222046',   'valentina.sosa@unamba.edu.pe', 'Valentina Sosa Apaza',     '900000007', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9),
  ('estudiante', '71234574', '223014',   'diego.torres@unamba.edu.pe',   'Diego Torres Mamani',      '900000008', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9),
  ('estudiante', '71234575', '231150',   'luis.navarro@unamba.edu.pe',   'Luis Navarro Cusihuaranga','900000009', '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9)
ON CONFLICT (email) DO NOTHING;

-- Aulas (RF-05) - laboratorios del horario de ejemplo
INSERT INTO room (code, name, building) VALUES
  ('LAB 104', 'Laboratorio 104', 'Facultad de Informática'),
  ('LAB 202', 'Laboratorio 202', 'Facultad de Informática'),
  ('LAB 304', 'Laboratorio 304', 'Facultad de Informática'),
  ('LAB 305', 'Laboratorio 305', 'Facultad de Informática'),
  ('LAB 306', 'Laboratorio 306', 'Facultad de Informática'),
  ('LAB 401', 'Laboratorio 401', 'Facultad de Informática')
ON CONFLICT (code) DO NOTHING;

-- Dispositivos demo (RF-05): una cámara y un ESP32 por aula.
-- device_key = identidad lógica con la que el ESP32 se presenta por WebSocket.
-- rtsp_url de ejemplo: reemplazar usuario/contraseña/IP por las reales.
INSERT INTO device (room_id, device_type, device_key, name, ip_address, mac_address, rtsp_url)
SELECT r.id, 'camara', 'cam-'   || lower(replace(r.code, ' ', '')), 'Cámara Hikvision ' || r.code, '10.14.5.' || (10 + r.id)::text, NULL,
       'rtsp://admin:Admin123@10.14.5.' || (10 + r.id)::text || ':554/Streaming/Channels/101'
FROM room r
WHERE NOT EXISTS (SELECT 1 FROM device d WHERE d.device_key = 'cam-' || lower(replace(r.code, ' ', '')));

INSERT INTO device (room_id, device_type, device_key, name, ip_address, mac_address)
SELECT r.id, 'esp32', 'esp32-' || lower(replace(r.code, ' ', '')), 'Nodo puerta ' || r.code, '10.14.6.' || (10 + r.id)::text, NULL
FROM room r
WHERE NOT EXISTS (SELECT 1 FROM device d WHERE d.device_key = 'esp32-' || lower(replace(r.code, ' ', '')));

-- Cursos del horario de ejemplo (RF-06)
INSERT INTO course (code, name) VALUES
  ('ISA901', 'Computación Gráfica'),
  ('ISA902', 'Sistemas Distribuidos'),
  ('ISA903', 'Inteligencia Artificial I'),
  ('ISA904', 'Programación Paralela'),
  ('ISA905', 'Metodología de la Investigación Científica'),
  ('ISA906', 'Interacción Humano Computador')
ON CONFLICT (code) DO NOTHING;

-- Grupo único (A) por curso con su docente y aula
INSERT INTO course_group (course_id, group_code, teacher_id, room_id)
SELECT c.id, 'A',
       (SELECT id FROM app_user WHERE email = CASE c.code
           WHEN 'ISA903' THEN 'aquino.mario@unamba.edu.pe'
           WHEN 'ISA905' THEN 'cari.francisco@unamba.edu.pe'
           ELSE 'aquino.mario@unamba.edu.pe' END),
       (SELECT id FROM room WHERE code = CASE c.code
           WHEN 'ISA901' THEN 'LAB 401'
           WHEN 'ISA902' THEN 'LAB 304'
           WHEN 'ISA903' THEN 'LAB 304'
           WHEN 'ISA904' THEN 'LAB 304'
           WHEN 'ISA905' THEN 'LAB 305'
           WHEN 'ISA906' THEN 'LAB 304' END)
FROM course c
WHERE NOT EXISTS (SELECT 1 FROM course_group g WHERE g.course_id = c.id AND g.group_code = 'A');

-- Bloques horarios (weekday: 1=Lun ... 5=Vie), según el horario de ejemplo.
-- Nota: ISA904 Jueves 11:00-13:00 se solapa con ISA906 (distinto aula y
-- distinto docente), por eso la restricción única es (weekday,start_time,end_time)
-- solo para la demo simplificada; la validación real de choques la hace la API.
INSERT INTO schedule_block (group_id, weekday, start_time, end_time)
SELECT g.id, v.weekday, v.start_time::time, v.end_time::time
FROM (VALUES
  -- ISA903 Inteligencia Artificial I (LAB 304) - Lun/Mié 07:00-09:00, Vie 11:00-13:00
  ('ISA903', 1, '07:00', '09:00'),
  ('ISA903', 3, '07:00', '09:00'),
  ('ISA903', 5, '11:00', '13:00'),
  -- ISA901 Computación Gráfica (LAB 401) - Mar/Jue 07:00-09:00, Vie 09:00-11:00
  ('ISA901', 2, '07:00', '09:00'),
  ('ISA901', 4, '07:00', '09:00'),
  ('ISA901', 5, '09:00', '11:00'),
  -- ISA905 Metodología (LAB 305) - Lun/Mié/Vie 09:00-11:00
  ('ISA905', 1, '09:00', '11:00'),
  ('ISA905', 3, '09:00', '11:00'),
  ('ISA905', 5, '09:00', '11:00'),
  -- ISA902 Sistemas Distribuidos (LAB 304) - Mar/Jue 09:00-11:00, Vie 14:00-16:00
  ('ISA902', 2, '09:00', '11:00'),
  ('ISA902', 4, '09:00', '11:00'),
  ('ISA902', 5, '14:00', '16:00'),
  -- ISA906 Interacción Humano Computador (LAB 304) - Lun/Mié 11:00-13:00
  ('ISA906', 1, '11:00', '13:00'),
  ('ISA906', 3, '11:00', '13:00'),
  -- ISA904 Programación Paralela - Jue 11:00-13:00 (LAB 304), Mar 14:00-16:00 (LAB 306)
  ('ISA904', 4, '11:00', '13:00'),
  ('ISA904', 2, '14:00', '16:00')
) AS v(course_code, weekday, start_time, end_time)
JOIN course c        ON c.code = v.course_code
JOIN course_group g  ON g.course_id = c.id AND g.group_code = 'A'
WHERE NOT EXISTS (
  SELECT 1 FROM schedule_block sb
  JOIN course_group g2 ON g2.id = sb.group_id
  JOIN course c2 ON c2.id = g2.course_id
  WHERE c2.code = v.course_code AND g2.group_code = 'A'
    AND sb.weekday = v.weekday AND sb.start_time = v.start_time::time
);

-- Matrículas de los 6 estudiantes en los 6 cursos (RF-03/RF-22)
INSERT INTO enrollment (student_id, group_id)
SELECT st.id, g.id
FROM app_user st
JOIN course_group g ON g.group_code = 'A'
WHERE st.role = 'estudiante'
ON CONFLICT (student_id, group_id) DO NOTHING;

COMMIT;
