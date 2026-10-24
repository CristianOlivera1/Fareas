BEGIN;

INSERT INTO app_settings (
    id, semester_label, semester_start, semester_end,
    face_match_threshold, dpi_alert_percent, dpi_limit_percent
)
VALUES (1, '2026-II', DATE '2026-08-17', DATE '2026-12-19', 0.550, 20.00, 30.00)
ON CONFLICT (id) DO NOTHING;
INSERT INTO app_user (
    role, dni, code, email, full_name, whatsapp,
    password_hash, must_change_password, semester
)
VALUES
    ('admin', '71234567', NULL, 'admin@unamba.edu.pe', 'Admin Fareas', '900000001',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('estudiante', '71234570', '221181', '221181@unamba.edu.pe', 'Cristian Olivera Chávez', '954306632',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, 9),

    ('docente', '80010001', 'DOC-003', 'manuel.ibarra@unamba.edu.pe', 'Manuel Jesús Ibarra Cabrera', '900000004',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010002', 'DOC-004', 'jose.merma@unamba.edu.pe', 'Jose Luis Merma Aroni', '900000005',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010003', 'DOC-005', 'erech.ordonez@unamba.edu.pe', 'Erech Ordoñez Ramos', '900000006',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010004', 'DOC-006', 'ecler.mamani@unamba.edu.pe', 'Ecler Mamani Vilca', '900000007',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010005', 'DOC-007', 'evelyn.luque@unamba.edu.pe', 'Evelyn Naida Luque Ochoa', '900000008',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010006', 'DOC-002', 'cari.francisco@unamba.edu.pe', 'Francisco Cari Incahuanaco', '900000003',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010007', 'DOC-008', 'marleny.peralta@unamba.edu.pe', 'Marleny Peralta Ascue', '900000009',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010008', 'DOC-009', 'hesmeralda.rojas@unamba.edu.pe', 'Hesmeralda Rojas Enriquez', '900000010',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010009', 'DOC-001', 'aquino.mario@unamba.edu.pe', 'Mario Aquino Cruz', '900000002',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010010', 'DOC-010', 'nora.echegaray@unamba.edu.pe', 'Nora Gladys Echegaray Peña', '900000011',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010011', 'DOC-011', 'lintol.contreras@unamba.edu.pe', 'Lintol Contreras Salas', '900000012',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010012', 'DOC-012', 'maryluz.cuentas@unamba.edu.pe', 'Maryluz Cuentas Toledo', '900000013',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010013', 'DOC-013', 'ebert.gomez@unamba.edu.pe', 'Ebert Gomez Aiquipa', '900000014',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010014', 'DOC-014', 'ronald.renteria@unamba.edu.pe', 'Ronald Alberto Renteria Ayquipa', '900000015',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010015', 'DOC-015', 'rafael.quispe@unamba.edu.pe', 'Rafael Ricardo Quispe Merma', '900000016',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010016', 'DOC-016', 'kevin.arias@unamba.edu.pe', 'Kevin Arnold Arias Figueroa', '900000017',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010017', 'DOC-017', 'yonatan.mamani@unamba.edu.pe', 'Yonatan Mamani Coaquira', '900000018',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010018', 'DOC-018', 'virgilio.martinez@unamba.edu.pe', 'Virgilio Martinez Duran', '900000019',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010019', 'DOC-019', 'yhon.fuentes@unamba.edu.pe', 'Yhon Fuentes Huaman', '900000020',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010020', 'DOC-020', 'wilson.mamani@unamba.edu.pe', 'Wilson Mamani Rodrigo', '900000021',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010021', 'DOC-021', 'luz.criado@unamba.edu.pe', 'Luz Liliana Criado Huaylla', '900000022',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010022', 'DOC-022', 'jezzy.pinto@unamba.edu.pe', 'Jezzy Pinto Espinoza', '900000023',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010023', 'DOC-023', 'julio.lloclli@unamba.edu.pe', 'Julio Cesar Lloclli Champi', '900000024',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010024', 'DOC-024', 'jorge.campos@unamba.edu.pe', 'Jorge Francisco Campos Malpartida', '900000025',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010025', 'DOC-025', 'yuliana.tomaylla@unamba.edu.pe', 'Yuliana Miriam Tomaylla Gutierrez', '900000026',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010026', 'DOC-026', 'alejandrina.huaylla@unamba.edu.pe', 'Alejandrina Huaylla Quispe', '900000027',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010027', 'DOC-027', 'betsabe.ccolqque@unamba.edu.pe', 'Betsabe Milagros Ccolqque Ruiz', '900000028',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010028', 'DOC-028', 'danyra.contreras@unamba.edu.pe', 'Danyra Contreras Meza', '900000029',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010029', 'DOC-029', 'harrison.ochoa@unamba.edu.pe', 'Harrison Ochoa Rivas', '900000030',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010030', 'DOC-030', 'cristhian.serrano@unamba.edu.pe', 'Cristhian Serrano Juro', '900000031',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010031', 'DOC-031', 'john.aguirre@unamba.edu.pe', 'John Abraham Aguirre Carrasco', '900000032',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010032', 'DOC-032', 'daryl.huamani@unamba.edu.pe', 'Daryl Andres Huamani Lopez', '900000033',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010033', 'DOC-033', 'wilber.quispe@unamba.edu.pe', 'Wilber Quispe Moscoso', '900000034',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010034', 'DOC-034', 'miguel.aquino@unamba.edu.pe', 'Miguel Angel Aquino Cruz', '900000035',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010035', 'DOC-035', 'eddy.orosco@unamba.edu.pe', 'Eddy Arnold Orosco Prada', '900000036',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL),

    ('docente', '80010036', 'DOC-036', 'hernan.ortega@unamba.edu.pe', 'Hernan Ortega Caceres', '900000037',
     '$argon2id$v=19$m=65536,t=3,p=4$Y83Nb/c+S4sUpDNl7+HSiQ$XPBBd5UN7GK+59zLDtUTjOMhy009pp3JDf/g5xazJ4k', FALSE, NULL)

ON CONFLICT (email) DO NOTHING;


INSERT INTO room (code, name, building) VALUES
  ('LAB 103', 'Laboratorio 103', 'Facultad de Informática'),
  ('LAB 104', 'Laboratorio 104', 'Facultad de Informática'),
  ('LAB 105', 'Laboratorio 105', 'Facultad de Informática'),
  ('LAB 206', 'Laboratorio 206', 'Facultad de Informática'),
  ('LAB 207', 'Laboratorio 207', 'Facultad de Informática'),
  ('LAB 208', 'Laboratorio 208', 'Facultad de Informática'),
  ('LAB 303', 'Laboratorio 303', 'Facultad de Informática'),
  ('LAB 304', 'Laboratorio 304', 'Facultad de Informática'),
  ('LAB 305', 'Laboratorio 305', 'Facultad de Informática'),
  ('LAB 306', 'Laboratorio 306', 'Facultad de Informática'),
  ('LAB 401', 'Laboratorio 401', 'Facultad de Informática')
ON CONFLICT (code) DO NOTHING;

INSERT INTO device (room_id, device_type, device_key, name, ip_address, mac_address, rtsp_url)
SELECT r.id, 'camara', 'cam-'   || lower(replace(r.code, ' ', '')), 'Cámara Hikvision ' || r.code, '10.14.5.' || (10 + r.id)::text, NULL,
       'rtsp://admin:Admin123@10.14.5.' || (10 + r.id)::text || ':554/Streaming/Channels/101'
FROM room r
WHERE NOT EXISTS (SELECT 1 FROM device d WHERE d.device_key = 'cam-' || lower(replace(r.code, ' ', '')))
ORDER BY r.id ASC
LIMIT 2;

INSERT INTO device (room_id, device_type, device_key, name, ip_address, mac_address)
SELECT r.id, 'esp32', 'esp32-' || lower(replace(r.code, ' ', '')), 'Nodo puerta ' || r.code, '10.14.6.' || (10 + r.id)::text, NULL
FROM room r
WHERE NOT EXISTS (SELECT 1 FROM device d WHERE d.device_key = 'esp32-' || lower(replace(r.code, ' ', '')))
ORDER BY r.id ASC
LIMIT 2;

INSERT INTO course (code, name, cycle) VALUES
  ('AIS11', 'Introducción a la informática y sistemas', 1),
  ('AGG1', 'Lengua castellana y argumentación', 1),
  ('AGG2', 'Matemática básica', 1),
  ('AGG3', 'Historia del Perú y del mundo', 1),
  ('AGG4', 'Geografía y recursos naturales', 1),
  ('AGG6', 'Filosofía y ética', 1),
  ('AGG7', 'Psicología', 1),
  ('AGG19', 'Dibujo en ingeniería I', 1),
  ('AIS21', 'Análisis y diseño de sistemas de información', 2),
  ('AGG20', 'Física I', 2),
  ('AIS22', 'Fundamentos de programación', 2),
  ('AIS23', 'Liderazgo y habildades sociales', 2),
  ('AGG5', 'Ecología y desarrolo sostenible', 2),
  ('AGG23', 'Cálculo diferencial', 2),
  ('AIS31', 'Matemática discreta I', 3),
  ('AIS32', 'Circuitos electrónicos', 3),
  ('AIS33', 'Estructura de datos', 3),
  ('AIS34', 'Base de datos I', 3),
  ('AIS35', 'Formulación de proyectos informáticos', 3),
  ('AGG22', 'Inglés', 3),
  ('AIS41', 'Matemática discreta II', 4),
  ('AIS42', 'Investigación de operaciones', 4),
  ('AIS43', 'Sistemas digitales', 4),
  ('AIS44', 'Programación orientada a objetos', 4),
  ('AIS45', 'Base de datos II', 4),
  ('AIS46', 'Gestión de proyectos ágiles', 4),
  ('AIS51', 'Cálculo integral', 5),
  ('AIS52', 'Incubadoras de empresas tecnológicas', 5),
  ('AIS53', 'Desarrollo de software I', 5),
  ('AIS54', 'Análisis y complejidad de algoritmos', 5),
  ('AIS55', 'Arquitectura del computador', 5),
  ('AGG21', 'Estadística y probabilidades', 5),
  ('AIS61', 'Álgebra lineal', 6),
  ('AIS65', 'Ingeniería de software I', 6),
  ('AIS64', 'Desarrollo de software II', 6),
  ('AIS63', 'Gerencia de proyectbs de tecnologias de información', 6),
  ('AIS62', 'Estadística inferencial', 6),
  ('AIS66', 'Sistemas operativos', 6),
  ('AIS71', 'Ecuaciones diferenciales', 7),
  ('AIS72', 'Simulación de sistemas', 7),
  ('AIS73', 'Ingeniería de software II', 7),
  ('AIS74', 'Minería de datos', 7),
  ('AIS75', 'Redes de computadoras', 7),
  ('AIS76', 'Robótica (Electivo)', 7),
  ('AIS77', 'Redacción de artículos cientficos (Electivo)', 7),
  ('AIS81', 'Metodología de la investigación', 8),
  ('AIS82', 'Telecomunicaciones', 8),
  ('AIS83', 'Interacción humano computador', 8),
  ('AIS84', 'Comercio electrónico y marketing digital', 8),
  ('AIS85', 'Fundamentos de inteligencia artificial', 8),
  ('AIS86', 'Arquitectura del software (Electivo)', 8),
  ('AIS87', 'Calidad del software (Electivo)', 8),
  ('AIS91', 'Seminario de tesis', 9),
  ('AIS92', 'Computación para móviles', 9),
  ('AIS93', 'Aprendizaje automático', 9),
  ('AIS94', 'Ciberseguridad', 9),
  ('AIS96', 'Programación de videojuegos (Electivo)', 9),
  ('AIS95', 'Programación paralela (Electivo)', 9),
  ('AIS01', 'Gestión de centro de datos', 10),
  ('AIS02', 'Computación en la nube', 10),
  ('AIS03', 'Big data', 10),
  ('AIS04', 'Investigación, desarrollo e innovación (l+D+i)', 10),
  ('AIS05', 'Informática forense (Electivo)', 10),
  ('AIS06', 'Ethical hacking (Electivo)', 10)
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

-- horarios
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
