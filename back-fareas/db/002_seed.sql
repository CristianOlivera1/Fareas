BEGIN;

INSERT INTO app_settings (
    id, semester_label, semester_start, semester_end,
    face_match_threshold, dpi_alert_percent, dpi_limit_percent
)
VALUES (1, '2026-II', DATE '2026-08-17', DATE '2026-12-19', 0.550, 20.00, 30.00)
ON CONFLICT (id) DO NOTHING;

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

INSERT INTO room (code, name, building) VALUES
  ('LAB 104', 'Laboratorio 104', 'Facultad de Informática'),
  ('LAB 202', 'Laboratorio 202', 'Facultad de Informática'),
  ('LAB 304', 'Laboratorio 304', 'Facultad de Informática'),
  ('LAB 305', 'Laboratorio 305', 'Facultad de Informática'),
  ('LAB 306', 'Laboratorio 306', 'Facultad de Informática'),
  ('LAB 401', 'Laboratorio 401', 'Facultad de Informática')
ON CONFLICT (code) DO NOTHING;

INSERT INTO device (room_id, device_type, device_key, name, ip_address, mac_address, rtsp_url)
SELECT r.id, 'camara', 'cam-'   || lower(replace(r.code, ' ', '')), 'Cámara Hikvision ' || r.code, '10.14.5.' || (10 + r.id)::text, NULL,
       'rtsp://admin:Admin123@10.14.5.' || (10 + r.id)::text || ':554/Streaming/Channels/101'
FROM room r
WHERE NOT EXISTS (SELECT 1 FROM device d WHERE d.device_key = 'cam-' || lower(replace(r.code, ' ', '')));

INSERT INTO device (room_id, device_type, device_key, name, ip_address, mac_address)
SELECT r.id, 'esp32', 'esp32-' || lower(replace(r.code, ' ', '')), 'Nodo puerta ' || r.code, '10.14.6.' || (10 + r.id)::text, NULL
FROM room r
WHERE NOT EXISTS (SELECT 1 FROM device d WHERE d.device_key = 'esp32-' || lower(replace(r.code, ' ', '')));

INSERT INTO course (code, name, cycle) VALUES
  ('ISA901', 'Computación Gráfica', 9),
  ('ISA902', 'Sistemas Distribuidos', 9),
  ('ISA903', 'Inteligencia Artificial I', 9),
  ('ISA904', 'Programación Paralela', 9),
  ('ISA905', 'Metodología de la Investigación Científica', 9),
  ('ISA906', 'Interacción Humano Computador', 9)
ON CONFLICT (code) DO NOTHING;

INSERT INTO course_group (course_id, group_code, teacher_id, semester_label)
SELECT c.id, 'A',
       (SELECT id FROM app_user WHERE email = CASE c.code
           WHEN 'ISA903' THEN 'aquino.mario@unamba.edu.pe'
           WHEN 'ISA905' THEN 'cari.francisco@unamba.edu.pe'
           ELSE 'aquino.mario@unamba.edu.pe' END),
       (SELECT semester_label FROM app_settings WHERE id = 1)
FROM course c
WHERE NOT EXISTS (
  SELECT 1 FROM course_group g
  WHERE g.course_id = c.id AND g.group_code = 'A'
    AND g.semester_label = (SELECT semester_label FROM app_settings WHERE id = 1)
);

INSERT INTO schedule_block (group_id, room_id, weekday, start_time, end_time)
SELECT g.id, r.id, v.weekday, v.start_time::time, v.end_time::time
FROM (VALUES
  ('ISA903', 1, '07:00', '09:00', 'LAB 304'),
  ('ISA903', 3, '07:00', '09:00', 'LAB 304'),
  ('ISA903', 5, '11:00', '13:00', 'LAB 304'),
  ('ISA901', 2, '07:00', '09:00', 'LAB 401'),
  ('ISA901', 4, '07:00', '09:00', 'LAB 401'),
  ('ISA901', 5, '07:00', '09:00', 'LAB 306'),
  ('ISA905', 1, '09:00', '11:00', 'LAB 305'),
  ('ISA905', 3, '09:00', '11:00', 'LAB 305'),
  ('ISA905', 5, '09:00', '11:00', 'LAB 305'),
  ('ISA902', 2, '09:00', '11:00', 'LAB 304'),
  ('ISA902', 4, '09:00', '11:00', 'LAB 304'),
  ('ISA902', 5, '14:00', '16:00', 'LAB 304'),
  ('ISA906', 1, '11:00', '13:00', 'LAB 304'),
  ('ISA906', 3, '11:00', '13:00', 'LAB 304'),
  ('ISA904', 4, '11:00', '13:00', 'LAB 304'),
  ('ISA904', 2, '14:00', '16:00', 'LAB 306')
) AS v(course_code, weekday, start_time, end_time, room_code)
JOIN course c        ON c.code = v.course_code
JOIN course_group g  ON g.course_id = c.id AND g.group_code = 'A'
JOIN room r          ON r.code = v.room_code
WHERE NOT EXISTS (
  SELECT 1 FROM schedule_block sb
  JOIN course_group g2 ON g2.id = sb.group_id
  JOIN course c2 ON c2.id = g2.course_id
  WHERE c2.code = v.course_code AND g2.group_code = 'A'
    AND g2.semester_label = (SELECT semester_label FROM app_settings WHERE id = 1)
    AND sb.weekday = v.weekday AND sb.start_time = v.start_time::time
);

INSERT INTO enrollment (student_id, group_id)
SELECT st.id, g.id
FROM app_user st
JOIN course_group g ON g.group_code = 'A'
WHERE st.role = 'estudiante'
ON CONFLICT (student_id, group_id) DO NOTHING;

COMMIT;
