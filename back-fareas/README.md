# Fareas API (backend)

Backend FastAPI del sistema de control de asistencia con reconocimiento facial -
Facultad de Informática, UNAMBA (Abancay, Apurímac).

- Requerimientos: `../Functional-requirements.md` (RF-01 … RF-35, Tabla 8 de veredictos)
- Plan de implementación: `../PLAN-BACKEND.md`

## Stack (todo nativo en Windows, sin Docker)
- **Python 13.13.14 o 13.13.15** 
- **FastAPI + Uvicorn** (Python 3.13, entrypoint con `fastapi` CLI)
- **PostgreSQL 17** (instalador oficial EDB) + **asyncpg** + **SQLModel**
- **ONNX Runtime (CPU)**: SCRFD `det_10g.onnx` (detección) + ArcFace `w600k_r50.onnx` (embeddings 512-d, pack buffalo_l)
- **WebSocket** con los ESP32 de las puertas (RF-25 / RF-33)
- Embeddings en columna `REAL[512]`; similitud de coseno en NumPy (**sin pgvector**: 0.23 ms medidos contra 5000 alumnos)

## Estructura

```
back-fareas/
├── pyproject.toml            # deps + [tool.fastapi] entrypoint = app.main:app
├── main.py                   # shim: la app real vive en app/main.py
├── app/
│   ├── main.py               # create_app(), lifespan, CORS, routers
│   ├── core/config.py        # Settings (pydantic-settings) desde .env
│   ├── core/deps.py          # DbSession, CurrentUser (Bearer), RequireRole (RF-01)
│   ├── core/security.py      # argon2 (pwdlib) + JWT (pyjwt)
│   ├── database.py           # engine asyncpg + SessionLocal (SQLModel)
│   ├── tables.py             # 15 entidades SQLModel que MAPEAN db/001_schema.sql
│   ├── schemas/              # DTOs: auth.py, common.py (Page/Message), …
│   ├── ai/                   # pipeline de visión (Bloque 5): detector, embedder,
│   │                         #   recognizer, pipeline (Tabla 8), frame_source, runtime
│   ├── services/             # lógica de negocio (routers delgados)
│   │   ├── accounts.py       # alta docente/estudiante + clave temporal (RF-02/03/08)
│   │   ├── audit.py          # bitácora RF-32 dentro de la transacción
│   │   ├── emailer.py        # credenciales (RF-08) y OTP (RF-12) vía SMTP
│   │   ├── notifications.py  # alertas DPI al cierre de sesión (RF-24)
│   │   ├── errors.py         # DomainError/ConflictError/NotFoundError → handlers HTTP
│   │   ├── attendance_engine.py  # resolver sesión, marca única, cierre RF-26, DPI RF-24
│   │   ├── session_scheduler.py  # APScheduler: cierre automático cada 60 s (RF-26)
│   │   ├── camera_loop.py    # cámaras RTSP → pipeline → marcas → ESP32 (2 fps)
│   │   ├── schedule.py       # validación de choques de horario (RF-06)
│   │   ├── ocr_schedule.py   # PDF de matrícula → bloques horarios (RF-07, Bloque 9)
│   │   └── exports.py        # reportes Excel/PDF con encabezado institucional (RF-16)
│   └── routers/
│       ├── auth.py           # login JWT (campo email), /me, cambio de clave, OTP (RF-11/RF-12)
│       ├── audit.py          # GET /audit-log (RF-32, solo admin, paginado)
│       ├── calendar_admin.py # feriados RF-09, justificaciones RF-10, settings RF-34
│       ├── catalog.py        # aulas, dispositivos, docentes, estudiantes (RF-02…RF-05, RF-35)
│       ├── courses.py        # cursos/grupos/bloques+choques, matrículas (RF-06, RF-22)
│       ├── attendance.py     # hoy (vista SQL), marca manual RF-21, rectificación RF-15
│       ├── dashboard.py      # summary, SSE en vivo y stats (RF-13, Bloque 8)
│       ├── reports.py        # descarga Excel/PDF de asistencia (RF-16, Bloque 8)
│       ├── health.py         # GET /api/v1/health (app + BD)
│       └── ws_devices.py     # WS ESP32 Bloque 7: hello/heartbeat/veredictos (RF-25/33/35)
├── db/                       # SQL MANUAL (ver "Actualizaciones de la base de datos")
│   ├── 001_schema.sql        # ESQUEMA COMPLETO Y VIGENTE (fuente de verdad)
│   ├── 002_seed.sql          # datos demo + parámetros vigentes (re-ejecutable)
├── models/                   # pesos .onnx (gitignored) - det_10g + w600k_r50
├── ai/                       # pipeline de visión (Bloque 5) - sin lógica HTTP
│   ├── boxes.py              # IoU + NMS en NumPy
│   ├── detector.py           # SCRFD det_10g (FPN 8/16/32, landmarks, NMS)
│   ├── embedder.py           # ArcFace w600k_r50 (alineación 112x112 → 512-d)
│   ├── recognizer.py         # galería en memoria + coseno (0.23 ms / 5000)
│   ├── pipeline.py           # process_frame() → veredicto Tabla 8
│   ├── runtime.py            # modelos una vez por proceso + recarga de galería
│   └── frame_source.py       # RTSP / MP4 / webcam (hilo + buffer de 1 frame)
├── storage/                  # fotos de enrolamiento en dev (prod: Cloudflare R2)
└── scripts/
    ├── test_rtsp.py          # prueba de la cámara Hikvision (RF-17)
    ├── simulate_camera.py    # demo con video en bucle o --save anotado
    └── simulate_esp32.py     # simulador del nodo ESP32 (Bloque 7)
```

## Puesta en marcha

```bash
cd back-fareas

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt

pip install "fastapi[standard]"

copy .env.example .env 

psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/001_schema.sql
psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/002_seed.sql

fastapi dev          # entrypoint de pyproject.toml (app.main:app)
# alternativas: uvicorn app.main:app --reload  |  python main.py
```

- Swagger: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health> →
  `{"status":"ok","database":"ok","users":9}` con el seed cargado

## Actualizaciones de la base de datos (regla del proyecto)

**Un cambio de BD se aplica con 2 scripts como máximo: `db/001_schema.sql` +
`db/002_seed.sql`.** No hay herramienta de migraciones (Alembic, Flyway): el
esquema se mantiene a mano, pero con estas reglas.

1. **`001_schema.sql` SIEMPRE se actualiza.** Es la fuente de verdad de la
   estructura y refleja la BD de desarrollo tal cual. Si el cambio toca el
   esquema (tabla, columna, índice, CHECK, vista, valor de enum), se deja al día
   **en el mismo commit** del cambio.
2. **`002_seed.sql` también**, si el cambio toca datos demo o parámetros (p. ej.
   `app_settings`: semestre, niveles DPI, umbral facial), o si agrega columnas
   `NOT NULL` a tablas que el seed llena.
3. **Para las BD que ya existen, además va un ALTER numerado nuevo**
   (`db/003_algo.sql`, `004_…`): el paso a paso para la BD que ya tiene datos.
   Debe ser **re-ejecutable** (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT
   EXISTS`, bloques `DO $$ … EXCEPTION WHEN duplicate_object THEN NULL; END $$`)
   y nunca recrea ni borra datos.
4. **Cuando todo el equipo ya aplicó el ALTER, SE BORRA** (su contenido ya vive
   en `001`) y se menciona en el commit. Así: un dev nuevo instala con 2
   scripts, y una BD vieja se pone al día con el ALTER pendiente + esos 2.
5. El `ADD VALUE` de un enum no se puede usar en la misma transacción que lo
   agrega: va en su propio archivo (por eso `006` existió como archivo aparte).

Lo que se revisa al actualizar (la comparación que prueba que `001` + `002`
reproducen la BD real):

```bash
# 1) DDL de la BD de desarrollo ya migrada = base para editar 001_schema.sql
pg_dump -U postgres -d fareas --schema-only --no-owner --no-acl > /tmp/fareas.sql

# 2) BD limpia + los 2 scripts; su DDL debe coincidir con el anterior
createdb -U postgres fareas_check
psql -U postgres -d fareas_check -v ON_ERROR_STOP=1 -f db/001_schema.sql
psql -U postgres -d fareas_check -v ON_ERROR_STOP=1 -f db/002_seed.sql
pg_dump -U postgres -d fareas_check --schema-only --no-owner --no-acl > /tmp/check.sql
diff /tmp/fareas.sql /tmp/check.sql   # solo deben variar los SET/comentarios
dropdb -U postgres fareas_check
```

`001` y `002` se ejecutan sobre una BD **vacía**: no son idempotentes a nivel
de esquema (`CREATE TYPE/TABLE` fallan si los objetos ya existen).

## Usuarios demo (tras ejecutar 002_seed.sql)

Login por **correo** o por **código de matrícula**: `POST /api/v1/auth/login`

```json
{
  "email": "admin@unamba.edu.pe",
  "password": "12345678"
}
```

El campo `email` acepta también el código de matrícula (p. ej. `"email": "221181"`).

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin@unamba.edu.pe` | `12345678` | admin |
| `aquino.mario@unamba.edu.pe` | `12345678` | docente |
| `221181` | `12345678` | estudiante (código) |

Endpoints de auth: `POST /auth/login` · `GET /auth/me` · `POST /auth/change-password`
· `POST /auth/recover` → `/verify` → `/reset` (OTP 6 dígitos, RF-12).

### Endpoints del Bloque 4 - catálogo académico (RF-02…RF-10, RF-22, RF-32, RF-34, RF-35)

- **Aulas:** `GET/POST /rooms` · `PATCH /rooms/{id}` - paginado con `?page=&page_size=&q=`
- **Dispositivos:** `GET/POST /devices` · `PATCH /devices/{id}` · `GET /devices/status` (público, RF-35)
- **Docentes:** `GET/POST /teachers` (alta envía clave temporal por correo, RF-08)
- **Estudiantes:** `GET/POST /students` (`?semester=` para filtrar por ciclo)
- **Cuentas:** `GET/PATCH /accounts/{id}` · `POST /accounts/{id}/send-temp-password` (reenvía credenciales RF-08)
- **Cursos/grupos/bloques:** `GET/POST /courses` · `GET /courses/{id}/groups` · `POST /courses/{id}/groups`
  · `GET/POST /groups/{id}/blocks` · `PATCH/DELETE /blocks/{id}` · `DELETE /groups/{id}` -
  **choques RF-06:** misma aula o mismo docente en rangos que se cruzan → 409; grupos paralelos válidos
- **Matrículas RF-22:** `GET/POST /groups/{id}/students` · `DELETE /groups/{id}/students/{student_id}`
- **Calendario:** `GET/POST /holidays` · `DELETE /holidays/{id}` · `GET/POST /justifications`
  · `DELETE /justifications/{id}` · `GET/PATCH /settings` (RF-34)
- **Bitácora RF-32:** `GET /audit-log` (solo admin; filtros `action`, `entity`, `entity_id`, `actor_id`, `since`)

Toda escritura queda registrada en `audit_log` con actor, IP y valores antes/después (JSONB).

### Bloque 5 - enrolamiento facial (RF-04) y pipeline de visión

- `POST /students/{id}/faces` - 3–5 fotos **base64** (JSON `{"photos": [...]}`).
  Exige 1 rostro por foto y consistencia intra-alumno (mín. 0.55 por pares);
  guarda el PROMEDIO normalizado en `face_embedding` y la portada en `storage/`.
- `GET /students/{id}/faces` - estado de enrolamiento (admin y docente).
- Umbral de reconocimiento RF-20 calibrado: **0.55** (misma persona ≥ 0.55,
  impostores < 0.35); editable por el admin vía `PATCH /settings` (RF-34).

```bash
# Demo sin hardware: video en bucle como puerta del aula (galeria desde BD)
python scripts/simulate_camera.py
# ...o generar el video anotado para la tesis
python scripts/simulate_camera.py video.mp4 --save anotado.mp4
```

> El `.env` de desarrollo trae `MAIL_ENABLED=false`: los correos (OTP, credenciales)
> no salen de verdad, se registran en los logs. Pon `true` para envío real.

## Tests

```bash
cd back-fareas
.venv/Scripts/python -m pytest tests/ -v
```

7 tests de autenticación corren contra la BD `fareas` real usando un usuario
temporal que se crea y elimina solo (no toca los datos del seed).

### Bloque 6 — motor de asistencia (RF-21…RF-26)

- `GET /attendance/today?course=&room=&status=` — registros del día (vista `v_today_attendance`).
- `POST /sessions/{id}/manual-mark` — RF-21: marca manual del docente (solo en SUS grupos).
- `PATCH /attendance/{id}/rectify` — RF-15: rectifica el estado con motivo obligatorio (audit_log).
- `POST /sessions/{id}/close` — RF-26: cierre manual (admin); el automático corre cada 60 s
  (APScheduler) y genera faltas a matriculados sin registro + alertas DPI (RF-24).
- Clasificación RF-23 (**R2, Bloque 11**): `asistio` entre `inicio − apertura
  anticipada` y `inicio + tolerancia`; `tardanza` después de eso y hasta el **fin
  del bloque** (55 min tarde en 1 h = tardanza, no falta); `falta` la genera el cierre.

La suite completa es de **101 tests**: auth (7) + catálogo (9) +
cursos/choques/matrículas (4) + calendario/parámetros/auditoría (5) +
visión y enrolamiento (15) + motor de asistencia y su API (9) + WebSocket
de dispositivos (4) + dashboard/SSE/reportes (7) + importación OCR (7) +
**reglas del Bloque 11 (29)**: ventana R2 y niveles DPI (2), ciclo de vida de
sesiones R3/R4/R5/R10 (5), justificaciones y rectificación R6/R11 (5),
matrículas R8/R9 (4), DPI R7 (4), seguridad/biometría R13/R14 (6) y
dashboard/feriados/reportes con las reglas nuevas (3).
Todos son idempotentes: crean sus propios datos temporales y los limpian.
Los smokes de visión se saltan solos si faltan los modelos ONNX o el video demo.

## Recursos

El video de la "puerta del aula" vive en `back-fareas/resources/` (fuera de
git por peso, pero DENTRO del proyecto). `scripts/simulate_camera.py` lo usa
por defecto y los smokes de visión lo cargan vía `app/ai/resources.py`.

### Bloque 7 — WebSocket de dispositivos ESP32 (RF-25, RF-33, RF-35)

Protocolo en `ws://localhost:8000/api/v1/ws/devices?token=<DEVICE_TOKEN_SECRET>`:

1. `hello` → el `device_id` DEBE existir como ESP32 activo en `device`
   (close 4404 si no; 4401 con token inválido). Marca `is_online=TRUE`.
2. `heartbeat` cada 30 s → actualiza `last_heartbeat`; sin latidos por 90 s el
   scheduler lo marca fuera de línea (RF-35, visible en `GET /devices/status`).
3. El backend despacha veredictos Tabla 8: `{type:verdict, status, color,
   buzzer, seconds, message}` — el firmware enciende el NeoPixel + buzzer.

```bash
# Simular el nodo desde la PC (emula el LED en consola)
.venv/Scripts/python -u scripts/simulate_esp32.py esp32-lab305 --intervalo 5
```

### Bloque 8 — Dashboard en vivo y reportes (RF-13, RF-16)

- `GET /dashboard/summary` — tarjetas: asistencias/tardanzas/ausencias de hoy,
  % de ausentismo, cámaras y alertas DPI (`v_student_dpi` + `app_settings`).
- `GET /dashboard/live?access_token=<JWT>&room_id=` — **SSE** con los veredictos
  Tabla 8 del bucle de cámaras. EventSource no puede mandar cabeceras: el JWT
  va por query y se valida rol docente/admin. Ídem `/dashboard/live-room/{room_id}`.
- `GET /stats/hourly?day=` — marcas por hora de inicio de bloque (franja 07–20).
- `GET /stats/distribution?desde=&hasta=` — dona asistio/tardanza/falta/sin_registro
  (`sin_registro` = matriculados de sesiones cerradas sin marca).
- `GET /reports/attendance.xlsx|pdf?desde=&hasta=&course_id=` — RF-16 con
  encabezado institucional; el docente solo descarga SUS grupos (RF-21).

### Bloque 9 — Importación de horarios por PDF (RF-07)

- `POST /courses/import-pdf` — subes la constancia de matrícula (multipart, solo admin);
  devuelve bloques horarios CANDIDATOS (curso, grupo, día, horas) con `confiable` y `nota`
  para lo ambiguo. **No persiste nada**: pantalla de revisión del RF-07.
- `POST /courses/import-pdf/confirm` — recibe la propuesta corregida + `teacher_id` + `room_id`;
  crea cursos/grupos/bloques con la misma validación de choques RF-06, **todo o nada** (rollback).
  Un PDF escaneado (sin texto) → 422 con explicación: RF-07 procesa constancias digitales.

  > Los grupos importados toman el **semestre vigente** (R1, Bloque 11).

### Bloque 11 — reglas de negocio (R1…R15)

> Las reglas R1…R15 ya viven dentro de `db/001_schema.sql`: los scripts
> `005_reglas_negocio.sql`, `006_session_cancelada.sql` y `007_vistas_reglas.sql`
> se consolidaron ahí y **se borraron el 2026-10-16** (ya los había aplicado
> todo el equipo). Si tu BD es anterior, aplica los ALTER pendientes y luego
> `001` + `002` (2 scripts, ver "Actualizaciones de la base de datos"), y
> reinicia el backend.

**Decisiones confirmadas (2026-10-11):** tardanza hasta el fin del bloque ·
inhabilitación **al superar** el 30 % (aviso ≥ 20 %) · cupo **40 para todos** ·
al transferirse de grupo las faltas anteriores **se conservan** · fechas del
semestre en `app_settings` (**2026-II: 2026-08-17 → 2026-12-19**, editables por
el admin con `PATCH /settings`).

- **Sesiones:** el scheduler abre la sesión al iniciar la ventana (R3) aunque
  nadie marque; al cierre con cero marcas queda `needs_review` sin faltas (R4) y
  se resuelve en `GET /attendance/sessions-review` → `confirmar_faltas | cancelar`.
  Cancelación con motivo (`POST /sessions/{id}/cancel`, `POST /blocks/{id}/cancel-day`
  con `fecha` opcional) — nunca genera faltas (R5).
- **Justificaciones (R6):** crear marca las faltas del rango (`is_justified` +
  `justification_id`) y las futuras nacen justificadas; eliminar revierte. El
  docente solo justifica a sus alumnos y con su curso; sin plazo.
- **DPI (R7):** `absence_percent` = faltas no justificadas / sesiones válidas;
  niveles 20/30; correo solo con ≥ 4 sesiones y **una vez por nivel** por
  semestre. `GET /dpi/at-risk`, `GET /students/{id}/dpi`, `GET /attendance/me/dpi`.
- **Matrículas (R8):** cupo, un grupo activo por curso, sin cruce de horarios,
  retiro con `withdrawn_at`, `POST /groups/{id}/students/{sid}/transfer`.
- **Rectificación (R11):** el docente solo los últimos 7 días; el admin sin plazo.
- **Seguridad (R14):** con clave temporal todo responde 403 `must_change_password`
  salvo `/auth/me` y `/auth/change-password`; usuario inactivo → 401 al instante;
  `rtsp_url` enmascarada en listados (completa en `GET /devices/{id}`).
- **Biometría (R13, Ley 29733):** `POST /students/{id}/faces` exige `consent: true`;
  `DELETE /students/{id}/faces` borra embeddings y foto.
- **Feriados (R12):** `POST /holidays/range` (rango, omite fines de semana) y
  `POST /holidays/national?year=` (fijos + Semana Santa, ajustables).
- **Reportes:** `GET /reports/group-matrix.xlsx?group_id=` (alumnos × fechas con
  **A/T/F/FJ/—**) y `GET /reports/dpi-risk.xlsx?course_id=` (alerta/límite).

## Scripts de hardware / simulación

```bash
# Cámara Hikvision real (sub-stream recomendado, menos CPU):
python scripts/test_rtsp.py "rtsp://admin:CLAVE@10.14.5.11:554/Streaming/Channels/102"

# Nodo ESP32 simulado (protocolo WS antes de tocar el hardware):
python scripts/simulate_esp32.py esp32-lab305
```

## Protocolo WebSocket de dispositivos (RF-25 / RF-33)

1. Conexión: `ws://localhost:8000/api/v1/ws/devices?token=<DEVICE_TOKEN_SECRET>`
2. Presentación: `{"type":"hello","device_id":"esp32-lab305"}` - debe coincidir
   con `device.device_key` en la BD. **Corrección del Bloque 11:** enviarlo en el
   evento `WStype_CONNECTED` (no en `setup()`).
3. Latido cada 30 s: `{"type":"heartbeat"}` → sin latidos por 90 s el nodo
   queda fuera de línea (RF-35).
4. Comando del backend (Tabla 8):
   `{"type":"verdict","status":"asistio","message":"Registro correcto","color":"verde","buzzer":"beep_1","seconds":3}`

> **Hardware (Bloque 11):** el buzzer va a **GPIO 26** (GPIO 12 es pin de
> arranque del ESP32). Reserva IP fija (DHCP) para la PC del backend; el ESP32
> solo usa WiFi de 2.4 GHz. El veredicto `azul` (sin clase/desconocido) no lleva
> beeps, solo la animación del anillo.
