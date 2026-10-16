# PLAN DE IMPLEMENTACIÓN - BACKEND FAREAS (Angular + FastAPI + PostgreSQL 17)

> Proyecto académico: Control de asistencia con reconocimiento facial - Facultad de Informática, UNAMBA.
> Principio rector: **profesional y técnico, no empresarial**. Un monolito modular en FastAPI. Sin Redis, sin Celery, sin workers externos, **sin Alembic**, **sin pgvector**, **sin Docker**. Cada bloque termina con algo ejecutable y verificable.

---

## 0. Estado actual (progreso ya completado y verificado)

| ✅ Hecho | Detalle |
|---|---|
| Base de datos creada | PostgreSQL **17.11** (instalador oficial Windows). BD `fareas` creada y migrada |
| Esquema completo | `back-fareas/db/001_schema.sql` ejecutado: 14 tablas, 4 enums, vistas `v_today_attendance` y `v_student_dpi` |
| Datos demo cargados | `back-fareas/db/002_seed.sql`: 1 admin + 2 docentes + 6 estudiantes, 6 aulas, 12 dispositivos, 6 cursos (ISA901…ISA906), 16 bloques horarios, 36 matrículas |
| Modelos ONNX en su sitio | `back-fareas/models/`: `det_10g.onnx` (17 MB, SCRFD) + `w600k_r50.onnx` (174 MB, ArcFace 512-d) - copiados desde tus descargas |
| Stack instalado | SQLModel, asyncpg, APScheduler, opencv-python 4.10, onnxruntime 1.20, numpy 2.1, openpyxl, reportlab, pdfplumber - todos importan OK en el venv |
| Modelos probados | Ambos `.onnx` cargan en CPU (0.1 s / 0.3 s); ArcFace salida confirmada: vector **[1, 512]** |
| Búsqueda vectorial validada | Benchmark NumPy: **0.23 ms** por búsqueda contra 5000 alumnos (la opción sin pgvector sobra para la facultad) |
| Configuración | `.env` con `postgresql+asyncpg://postgres:***@localhost:5432/fareas`, JWT, SMTP, umbral facial 0.75, `DEVICE_TOKEN_SECRET` |
| **Bloque 1 completado** | `app/main.py` + `pyproject.toml` (entrypoint `fastapi dev`), `database.py` (SQLModel async), `core/deps.py`, `tables.py` (14 entidades SQLModel con enums nativos), scripts `test_rtsp.py` y `simulate_esp32.py`. Verificado con servidor uvicorn real: `GET /api/v1/health` → `{"database":"ok","users":9}`. Ruff limpio |

### Decisiones definitivas

1. **Sin pgvector** - embeddings en columna `REAL[512]`; similitud coseno en NumPy (0.23 ms medidos). El archivo `requirements.txt` **ya no incluye pgvector** ✔. El SQL que se genera en el futuro (migraciones manuales) tampoco lo requiere.
2. **Sin Alembic** - la BD se crea/actualiza con **scripts SQL manuales numerados** en `back-fareas/db/` que tú ejecutas en pgAdmin o psql. Detalle en §1.
3. **Sin Docker** - todo nativo en Windows: PostgreSQL (instalador oficial), Python en `.venv`, OpenCV/ONNX Runtime vía pip. Docker queda descartado para este proyecto.
4. **No se entrena ningún modelo** - pesos preentrenados buffalo_l; el "aprendizaje" del sistema es el enrolamiento (RF-04).

---

## 1. Gestión de la base de datos sin migraciones automáticas

```
back-fareas/db/
├── 001_schema.sql    # esquema completo (idempotente: DROP IF EXISTS + CREATE)
├── 002_seed.sql      # datos demo (idempotente: ON CONFLICT DO NOTHING)
└── 003_..., 004_...  # ACTUALIZACIONES futuras: un archivo por cambio
```

**Convención de actualizaciones (`003_xxx.sql` en adelante):**

```sql
-- ============================================================================
-- FAREAS - 003_agregar_campo_x.sql  (2026-10-05)
-- Motivo: <qué se necesita y por qué>
-- Ejecutar manualmente en pgAdmin (Query Tool sobre "fareas") o:
--   psql -U postgres -d fareas -f db/003_agregar_campo_x.sql
-- ============================================================================
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
```

- **Un archivo por cambio**, numerado secuencialmente; nunca se edita `001` después de haberlo aplicado.
- Cada script debe ser **re-ejecutable sin romper** (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `DO $$ ... EXCEPTION ... $$` para datos).
- Los modelos Python (SQLModel) **mapean** estas tablas pero **jamás ejecutan `create_all()`**: la BD manda, el código se adapta.
- Yo genero el script `00N_*.sql`, **te aviso**, y tú lo ejecutas en pgAdmin (o me das permiso y lo ejecuto por psql).

---

## 2. Estructura de carpetas (profesional y moderna, skill oficial FastAPI)

Monolito modular por dominio; routers con `prefix`/`tags`/dependencias a nivel router; DTOs Pydantic (`schemas/`) separados de las entidades SQLModel; dependencias `Annotated`; entrypoint con `fastapi` CLI vía `[tool.fastapi]`.

```
back-fareas/
├── pyproject.toml                  # deps + [tool.fastapi] entrypoint + [tool.ruff]
├── .env                            # configuración real (NUNCA versionar)
├── .env.example                    # template sin credenciales
├── requirements.txt                # SIN pgvector (ya actualizado)
├── README.md
├── db/                             # SQL manual (ver §1) - 001, 002, 003…
├── models/                         # pesos .onnx (gitignored) - ya poblado
│   ├── det_10g.onnx
│   └── w600k_r50.onnx
├── storage/                        # fotos de enrolamiento en dev (prod: Cloudflare R2) - gitignored
├── app/
│   ├── __init__.py
│   ├── main.py                     # create_app() + lifespan (scheduler, routers, app.frontend() en prod)
│   ├── core/
│   │   ├── config.py               # Settings (pydantic-settings) - existe, se amplía
│   │   ├── security.py             # argon2 (pwdlib) + JWT (pyjwt)
│   │   └── deps.py                 # DbSession, CurrentUser, RequireRole - estilo Annotated
│   ├── database.py                 # engine asyncpg + SessionLocal + get_db (consolida db/session.py actual)
│   ├── tables.py                   # entidades SQLModel que MAPEAN las tablas de db/001 (sin create_all)
│   ├── schemas/                    # DTOs de entrada/salida
│   │   ├── auth.py  catalog.py  attendance.py  dashboard.py
│   ├── services/                   # lógica de negocio (routers delgados)
│   │   ├── emailer.py              # credenciales temporales (RF-08), OTP (RF-12), alertas DPI (RF-24)
│   │   ├── attendance_engine.py    # corazón: RF-21…RF-26 (sesión, marca única, clasificación, Tabla 8)
│   │   ├── session_scheduler.py    # cierre automático RF-26 (APScheduler en el lifespan)
│   │   ├── exports.py              # RF-16: Excel (openpyxl) + PDF (reportlab)
│   │   └── ocr_schedule.py         # RF-07: pdfplumber + regex
│   └── routers/
│       ├── health.py               # ya existe - se conecta a la BD real
│       ├── auth.py                 # login, cambio de clave, OTP (RF-11/RF-12)
│       ├── catalog.py              # docentes, estudiantes, aulas, dispositivos (RF-02…RF-05, RF-35)
│       ├── courses.py              # cursos, grupos, bloques + choques, matrículas (RF-06/RF-22)
│       ├── enrollment_faces.py     # fotos + embeddings (RF-04)
│       ├── attendance.py           # registros, rectificación (RF-15), justificaciones (RF-10)
│       ├── dashboard.py            # summary + live SSE + stats (ver §5)
│       ├── reports.py              # Excel/PDF (RF-16)
│       ├── calendar_admin.py       # feriados (RF-09), parámetros (RF-34)
│       ├── ws_devices.py           # WebSocket ESP32 (existe; se extiende RF-25/RF-33)
│       └── audit.py                # bitácora RF-32 (lectura admin)
├── ai/                             # pipeline de visión - sin lógica HTTP
│   ├── frame_source.py             # RTSP | archivo MP4 | webcam (misma interfaz)
│   ├── detector.py                 # SCRFD det_10g.onnx (pre-procesado + decodificación)
│   ├── embedder.py                 # ArcFace w600k_r50.onnx → 512-d normalizado
│   ├── recognizer.py               # coseno NumPy contra face_embedding (0.23 ms / 5000)
│   └── pipeline.py                 # frame → detectar → embeddear → identificar → veredicto Tabla 8
├── scripts/
│   ├── test_rtsp.py                # prueba rápida de la cámara real (ver §4)
│   ├── simulate_camera.py          # MP4 en bucle como si fuera la puerta del aula (demo sin hardware)
│   └── simulate_esp32.py           # finge un ESP32 por WebSocket para probar la puerta en PC
└── tests/
    ├── conftest.py                 # httpx.AsyncClient + BD fareas_test
    ├── test_attendance_engine.py   # cada fila de la Tabla 8 como caso
    └── test_auth.py
```

---

## 3. Bloques de implementación (orden estricto)

### Bloque 1 - Fundaciones de la app (½ día) - **✅ COMPLETADO Y VERIFICADO**
- [x] `app/main.py` + `pyproject.toml` con `[tool.fastapi] entrypoint = "app.main:app"`; `main.py` raíz quedó como shim de compatibilidad.
- [x] `database.py` (SQLModel AsyncSession sobre asyncpg, `pool_pre_ping`) + `core/deps.py` (`DbSession` con `Annotated`).
- [x] `tables.py`: 14 entidades SQLModel mapeando `001_schema.sql` (enums PG nativos con `create_type=False` y `values_callable`, sin `create_all`).
- [x] Ruff configurado y limpio; `GET /api/v1/health` verificado contra la BD real con servidor uvicorn: `{"status":"ok","database":"ok","users":9}`.
- [x] Scripts de hardware creados: `scripts/test_rtsp.py` (cámara, §4.1) y `scripts/simulate_esp32.py` (protocolo WS, §4.2).

**Problemas encontrados y corregidos durante la verificación (lección para los siguientes bloques):**
1. SQLAlchemy vincula por defecto los *nombres* de los miembros del enum (`ESTUDIANTE`) en vez de los *valores* (`estudiante`) → PostgreSQL rechaza el bind. Corregido con `values_callable` en `pg_enum()`.
2. La sesión de SQLAlchemy no tiene `.exec()`: hay que usar la `AsyncSession` de **SQLModel** en el sessionmaker.
3. Los emojis en `print()` del lifespan crashean el servidor real en consola Windows (cp1252) - el TestClient no lo revela. Sin emojis en logs.

- **Entregable:** `fastapi dev` levanta contra tu PostgreSQL y health dice `database: ok` ✔

### Bloque 2 - Esquema y datos - **✅ COMPLETADO**
- ✅ `db/001_schema.sql` + `db/002_seed.sql` ejecutados y verificados (9 usuarios, 16 bloques, 36 matrículas, 12 dispositivos).
- Nota: la contraseña demo de todos es `12345678` (argon2id). El login del frontend seguirá aceptando `admin/docente/estudiante + 123456` hasta conectar el backend (Bloque 3); después se usan los usuarios de la BD.

### Bloque 3 - Autenticación (1 día) - RF-01, RF-11, RF-12 - **✅ COMPLETADO Y VERIFICADO**
- [x] `core/security.py`: argon2 (pwdlib, formato PHC igual al seed) + JWT HS256 (`sub`, `role`, 120 min).
- [x] `routers/auth.py`: `POST /auth/login` (por email **o** código de matrícula), `GET /auth/me`, `POST /auth/change-password` (apaga `must_change_password`, RF-11), `POST /auth/recover` + `/verify` + `/reset` (OTP 6 dígitos, TTL 10 min, máx. 5 intentos, respuesta uniforme que no revela si el correo existe - RF-12).
- [x] `core/deps.py`: `CurrentUser` (Bearer) y `RequireRole(...)` para los routers del Bloque 4 (RF-01).
- [x] `services/emailer.py`: aiosmtplib con `MAIL_ENABLED=false` en desarrollo (registra el contenido sin enviar; ⚠️ rota la clave del Gmail, §6).
- [x] `tests/test_auth.py`: **7/7 tests** contra la BD `fareas` real (login, /me, cambio de clave, OTP completo, reset sin verificar OTP rechazado), con usuario temporal creado y limpiado por fixtures.

**Lecciones del bloque (documentadas para los siguientes):**
1. Las columnas `DEFAULT NOW()` deben declararse con `server_default=text("now()")` en `tables.py`, o el ORM envía NULL explícito y viola el NOT NULL (pisaría el default de la BD).
2. En pruebas, TODO en un solo event loop: `httpx.AsyncClient` + `ASGITransport`. Mezclar `TestClient` con sesiones del pool en otro loop corrompe asyncpg (`Event loop is closed`); el engine se hace `dispose()` tras cada test (fixture autouse).

- **Entregable:** login de los 3 roles contra la BD verificado con servidor uvicorn real (token JWT emitido y `/auth/me` respondiendo) ✔

### Bloque 4 - Catálogo académico (1–2 días) - RF-02…RF-06, RF-09, RF-10, RF-32, RF-34, RF-35 - **✅ COMPLETADO Y VERIFICADO**
- [x] CRUDs de aulas (`/rooms`), dispositivos (`/devices`, `/devices/status` público RF-35), docentes (`/teachers`) y estudiantes (`/students`), con paginación (`?page=&page_size=&q=`).
- [x] RF-08: alta de docente/estudiante genera **clave temporal** y la envía por correo (`services/accounts.py`); `POST /accounts/{id}/send-temp-password` la reenvía con clave nueva.
- [x] Cursos → grupos → bloques con **validación de solapamientos** en `services/schedule.py`: rechaza misma aula o mismo docente en rangos que se cruzan; grupos paralelos (aula y docente distintos) SÍ se permiten (Tabla 2).
- [x] Matrículas RF-22: `POST/DELETE /groups/{id}/students`, listado `/groups/{id}/students`.
- [x] Feriados RF-09 (`/holidays`), justificaciones por rango RF-10 (`/justifications`), parámetros RF-34 (`GET/PATCH /settings`).
- [x] Bitácora RF-32: TODAS las escrituras del catálogo llaman `services/audit.py` dentro de su transacción; lectura admin paginada en `GET /audit-log` (`routers/audit.py`) con filtros action/entity/actor/desde.
- [x] Login RF-11: campo renombrado `username` → `email` (acepta correo O código de matrícula; documentado en el schema y el README).
- [x] Ideas rescatadas del proyecto Laravel del usuario, adaptadas a FastAPI: Resources→`schemas/` (ya existía), ApiResponseHelper→`schemas/common.py` (`MessageResponse`, `Page[T]`), PaginationHelper→`core/pagination.py` (`PageParamsDep`), excepciones de Services (`InsufficientCreditsException`)→`services/errors.py` (`DomainError/ConflictError/NotFoundError`) mapeadas a HTTP por handlers globales en `main.py`, Validators/Rules→constraints Pydantic nativos, Observers→`services/audit.py`, Console/Commands→`scripts/`.
- [x] `tests/test_catalog.py`, `tests/test_courses.py`, `tests/test_calendar_audit.py`: **25/25 tests** en la suite completa (7 de auth + 18 nuevos), idempotentes contra la BD real. Verificado además con uvicorn real: login, paginación, aula, curso→grupo→bloque y audit_log con JSONB.

**Lecciones del bloque (para Bloques 5+):**
1. `page_params()` como valor por defecto NO se resuelve: la dependencia debe anotarse `Annotated[PageParams, Depends(page_params)]` (`PageParamsDep`), o el endpoint recibe el objeto `Query` crudo.
2. Nunca envolver endpoints con decoradores que cambien la firma (`*args, **kwargs`): FastAPI pierde los parámetros y exige `"args": Field required` en el body. El manejo de errores de dominio va por **exception handlers globales** en `main.py`.
3. `audit_log.old_value/new_value` son JSONB: mapearlos con `Column(JSONB)` y pasar dicts nativos (no strings JSON).
4. El usuario edita la BD demo mientras desarrollamos: los tests NO deben depender de correos del seed - crean sus propios actores (`docente_headers`) y se limpian solos (idempotentes).

- **Entregable:** cargar toda la malla del semestre desde Swagger sin romper restricciones ✔ (validado con tests + servidor real)

### Bloque 5 - Pipeline de visión (2 días) - RF-04, RF-17…RF-20 - **✅ COMPLETADO Y VERIFICADO**
- [x] `ai/frame_source.py`: RTSP / MP4 / webcam bajo una misma interfaz; lectura en HILO con buffer de 1 frame (siempre el más reciente; los endpoints HTTP nunca se bloquean). MP4 repite en bucle para demos.
- [x] `ai/detector.py`: SCRFD `det_10g.onnx` decodificado a mano (3 niveles FPN 8/16/32, 2 anclas/celda, distancias→cajas, landmarks→5 puntos, NMS NumPy). La agrupación de salidas se hace por FORMA (score dim 1 / bbox dim 4 / kps dim 10) porque el export usa nombres numéricos ('448','471',…).
- [x] `ai/embedder.py`: ArcFace `w600k_r50.onnx` con alineación `estimateAffinePartial2D` de los 5 landmarks → 112×112 → 512-d L2-normalizado (equivale a `cv2.SimilarityTransform` de contrib, sin instalar opencv-contrib).
- [x] `ai/recognizer.py`: `FaceGallery` en memoria (embeddings vigentes, recarga al enrolar) + coseno vectorizado NumPy; `ai/runtime.py` carga los modelos UNA vez por proceso (imports perezosos: onnxruntime pesa ~2 s).
- [x] `ai/pipeline.py`: `process_frame()` → veredicto Tabla 8 (verde/beep_1 asistió, amarillo/beep_2 tardanza, ROJO/tono_denegado para conocido NO matriculado, azul sin clase/desconocido) + cooldown por alumno + `as_ws_command()` listo para el ESP32 (Bloque 7).
- [x] `routers/enrollment_faces.py` + `services/faces.py`: 3–5 fotos base64 → exige exactamente 1 rostro por foto, consistencia intra-alumno por pares (mín 0.55), PROMEDIO normalizado a `face_embedding` (`REAL[512]`), portada en `storage/`, reemplazo del embedding anterior (`is_current`), auditoría RF-32 y recarga de galería en caliente.
- [x] `scripts/simulate_camera.py`: MP4 en bucle como puerta del aula; ventana con cajas coloreadas o `--save video_anotado.mp4` para la tesis.
- [x] Tests `tests/test_vision.py` + `tests/test_enrollment.py`: NMS/IoU, galería, veredictos Tabla 8 con dobles, E2E de la API RF-04 y 2 smokes con los MODELOS REALES + video de demo.
- Nota: el bucle 2 fps por aula activa con `asyncio.Queue` se mueve al Bloque 6 (ahí vive el motor de sesiones que lo consume; en B5 el script de demo procesa directo).

**Lecciones del bloque (para Bloques 6+):**
1. `REAL[512]` con asyncpg exige lista Python de floats: un literal str `'{0.1,...}'` falla con `DatatypeMismatch`. Resuelto con el tipo `PgRealArray` en `tables.py` (a la lectura llega `list[float]` nativo).
2. Umbral RF-20 recalibrado empíricamente: **0.55** (misma persona multi-pose ≥ 0.55; impostores < 0.35). El 0.75 del diseño dejaba 'desconocidos' a alumnos legítimos. Aplicado en `.env`, `.env.example` y BD (`db/004_umbral_facial_055.sql`).
3. Enrolar con UNA foto frontal alcanza ~0.19 del video de prueba; con el PROMEDIO de 4 poses multi-escala se identifica 20/22 frames con rostro - la regla RF-04 de 3–5 fotos es correcta y necesaria.
4. La invariancia de escala la da la ALINEACIÓN por landmarks (0.978 entre escalas), no el detector; sin `estimateAffinePartial2D` el reconocimiento degrada a ~0.5.
5. Los procesos uvicorn de prueba quedan vivos tras `kill %1` (Git Bash en Windows no siempre mata el árbol): verificar con `netstat -ano | grep :PUERTO` antes de relanzar o el server nuevo no podrá bindear (error 10048 silencioso).

- **Entregable:** alumno 221181 enrolado por API con 4 fotos del video demo → el pipeline lo identifica en vivo (video anotado `Downloads/fareas_demo_anotado.mp4`); 40/40 tests ✔

### Bloque 6 - Motor de asistencia (1–2 días) - RF-21…RF-26 - *el corazón* - **✅ COMPLETADO Y VERIFICADO**
- [x] `services/attendance_engine.py` (lógica pura, testeable): `resolver_sesion(aula, now)` (cámara→aula→grupos activos→bloque vigente→`attendance_session` del día; NO abre en feriados RF-09 ni fuera del horario RF-34) → marca ÚNICA (`UNIQUE(session_id, student_id)`) → clasificación RF-23 ~~dentro del bloque~~ → **R2 (Bloque 11, 2026-10-11): `asistio` entre `inicio − apertura anticipada` y `inicio + tolerancia`; `tardanza` después de eso y hasta el `fin` del bloque; luego la ventana cierra y la falta la genera el cierre (RF-26). La sesión la abre el scheduler (R3).**
- [x] `services/session_scheduler.py`: APScheduler en el `lifespan` (cada 60 s); **R3/R4 (Bloque 11): `abrir_sesiones_del_dia()` abre la sesión al iniciar su ventana de apertura (aunque nadie marque); `cerrar_sesiones_pendientes()` cierra al `fin` del bloque —incluidas las de fechas anteriores si el servidor estuvo caído—; con cero marcas queda `needs_review` SIN faltas, con marcas genera faltas (marked_at NULL) a los matriculados activos sin registro (nacen justificadas si hay justificación vigente, R6) y alertas DPI.**
- [x] Alertas DPI al cierre (RF-24): SQL sobre la vista `v_student_dpi` + `services/notifications.py` (correo con la paleta institucional, rojo si ya supera el 1/3).
- [x] `services/camera_loop.py`: un solo task asyncio en round-robin (~2 fps por aula activa) → pipeline → marca en BD → veredicto al ESP32 del aula + `ultimo_veredicto()` en memoria para el feed SSE del Bloque 8.
- [x] `routers/attendance.py`: `GET /attendance/today` (vista `v_today_attendance`, filtros curso/aula/estado — alimenta app-student-list, PLAN §5), `POST /sessions/{id}/manual-mark` (RF-21, docente solo en SUS grupos), `PATCH /attendance/{id}/rectify` (RF-15 motivo obligatorio → audit_log), `POST /sessions/{id}/close` (admin). (Bloque 6b añade `GET /attendance/sessions-today` y `GET /attendance/me`; ver arriba).
- [x] `tests/test_attendance_engine.py` + `test_attendance_api.py`: creación/reuso de sesión, feriado, ventana de tardanza, marca única (409), cierre con faltas e idempotencia, marca manual por API, rectificación auditada, 403 a docente ajeno.
- **Entregable VERIFICADO:** video demo → sesión auto-abierta → Raul (221181) identificado (sim 0.618) → marca `asistio` persistida → cierre sin faltas pendientes → todo en BD. **49/49 tests.**

**Lecciones del bloque (para Bloques 7+):**
1. Zona horaria: el motor usa hora Perú fija (UTC-5, sin DST). Las columnas TIMESTAMP (sin tz) RECHAZAN datetime aware (`closed_at`, `corrected_at` → `_naive_peru()`);
2. ~~RF-23: tardanza = llegar DESPUÉS del fin del bloque pero DENTRO de la tolerancia~~ → **REVISADO (Bloque 11, decisión 2026-10-11): tardanza = llegar después de `inicio + tolerancia` y antes del `fin` del bloque. Llegar 55 min tarde a un bloque de 1 h es tardanza, no falta.**
3. `db.exec()` de SQLModel NO acepta params posicionales: usar `text(...).bindparams(**params)`.
4. La BD demo la edita el usuario: los demos NUNCA deben asumir emails/códigos del seed.
5. Numeración de scripts BD: verificar `db/` antes de crear un 00N nuevo (003 ya estaba tomado por refresh tokens).

### Bloque 7 - ESP32 y dispositivos reales (1 día) - RF-25, RF-27…RF-29, RF-33 - **✅ COMPLETADO Y VERIFICADO**
- [x] `ws_devices.py` extendido: token por query (close 4401 si inválido), `hello` con `device_key` VALIDADO contra la tabla `device` (ESP32 activo; close 4404 si no existe), heartbeat que actualiza `last_heartbeat` en BD, desconexión y expiración (90 s sin latidos) marcan `is_online=FALSE` — visible en `GET /devices/status` (RF-35).
- [x] `session_scheduler.py` también ejecuta `expirar_nodos()` cada 60 s (RF-35).
- [x] `camera_loop.py` envía los veredictos Tabla 8 al device_key conectado vía `enviar_veredicto()`; clasificador RF-23 en vivo conectado al pipeline (asistio/tardanza/sin_registro por sesión) → las marcas faciales SÍ se persisten desde el bucle.
- [x] `scripts/simulate_esp32.py` actualizado: emula el anillo LED en consola (colores ANSI) y reporta cada veredicto.
- [x] Tests `test_ws_devices.py`: token inválido (4401), hello de key inexistente (4404), hello válido + heartbeat + ping + tipo desconocido, ciclo online→offline con expiración. **53/53 en la suite.**
- **Entregable VERIFICADO en demo end-to-end:** cámara de LAB 305 apuntando al video demo (dentro de `resources/`) → sesión auto-abierta → Raul identificado → `INSERT attendance_record (asistio, sim 0.656)` EN BD → ESP32 simulado recibió `[LED VERDE] buzzer=beep_1 — Registro correcto` (y azul para desconocidos, sin_rostro en escena vacía). Cuando conectes el ESP32 físico, el firmware de §4.2 habla el MISMO protocolo.

**Lecciones del bloque:**
1. Al abrir una fuente de video en hilo, ESPERAR el primer frame (warm-up ~5 s): sin eso cada `read()` llegaba vacío y la fuente se abría/cerraba en bucle.
2. El clasificador RF-23 debe conectarse al pipeline DEL BUCLE (por sesión/aula); sin él el pipeline está en modo demo y no genera `mark` (no persiste).
3. El buffering de stdout ocultaba los logs del simulador: correr con `python -u`.
4. Los close codes del WS en TestClient llegan como `WebSocketDisconnect(code)` en el cliente (no como dict).

### Bloque 8 - APIs del dashboard (1 día) - RF-13…RF-16 - **✅ COMPLETADO Y VERIFICADO**
- [x] `routers/dashboard.py`: `GET /dashboard/summary` (tarjetas RF-13: asistencias/tardanzas/ausencias de hoy, % ausentismo, cámaras, alertas DPI vía `v_student_dpi` + `app_settings`); feed EN VIVO con **SSE** (`EventSourceResponse` de sse-starlette, `ping=15`) retransmitiendo los veredictos de `camera_loop` (`/dashboard/live?access_token=&room_id=` y `/dashboard/live-room/{id}`) — el JWT va por QUERY porque EventSource no manda cabeceras (rol docente/admin validado a mano); `GET /stats/hourly?day=` (franja 07–20 por HORA DE BLOQUE) y `GET /stats/distribution?desde=&hasta=` (dona con `sin_registro` = matriculados de sesiones CERRADAS sin marca).
- [x] RF-15/RF-10 ya cubiertos en bloques previos (`attendance.py` rectifica con motivo→audit; justificaciones en `calendar_admin.py`), se reutilizaron.
- [x] `routers/reports.py` + `services/exports.py`: Excel (openpyxl) y PDF horizontal (reportlab) con encabezado institucional UNAMBA; `GET /reports/attendance.xlsx|pdf?desde=&hasta=&course_id=`; el docente solo exporta SUS grupos (mismo guard RF-21); StreamingResponse con Content-Disposition y funciones puras que devuelven bytes (testeables sin HTTP).
- [x] Tests `test_dashboard_reports.py` (7): summary, hourly/distribution, SSE sin token (422) / token inválido (401) / estudiante (403) / veredicto en vivo recibido, Excel (zip PK + openpyxl) y PDF (%PDF-), docente ajeno → reporte vacío. **60/60 en la suite.**
- **Entregable VERIFICADO E2E:** uvicorn real en :8010 → summary/hourly/distribution JSON correctos, SSE con `content-type: text/event-stream`, y `asistencia_2026-09-01_2026-09-27_*.xlsx` (magic 'Microsoft Excel 2007+') + PDF `%PDF-` descargados por curl.

**Lecciones del bloque:**
1. `GROUP BY status` sin calificar revienta con asyncpg (`AmbiguousColumnError`: `status` existe en record Y session) — siempre `GROUP BY ar.status` / `GROUP BY 1,2`.
2. `db.exec(text(...)).one()` devuelve Row (no escalar) → para COUNT usar `.scalar_one()`.
3. httpx+ASGITransport NO puede consumir un stream SSE infinito (se cuelga): en tests se llama al endpoint y se lee `resp.body_iterator.__anext__()` con `wait_for`, luego `aclose()`.
4. SQL del dashboard por HORA DE BLOQUE (no `marked_at`): la curva 07–20 muestra la carga real de la franja aunque la marca facial llegue minutos después.

### Bloque 9 - OCR de horarios (½ día) - RF-07 - **✅ COMPLETADO Y VERIFICADO**
- [x] `services/ocr_schedule.py`: `extraer_horarios(pdf_bytes)` con pdfplumber — estrategia por CONTEXTO DE LÍNEA: un código de curso (regex `A-Z{2,8}\d{2,4}`: ISA903, SI504…) fija curso actual; las líneas `DIA HH:MM - HH:MM` (día genérico de 3-4 letras, soporta `LUN/MIE`, guiones - – — y '8:00') generan bloques; `Grupo:`/`Sección:` en cualquier línea alimenta el contexto. Todo lo dudoso sale `confiable=False` + `nota` ('día no reconocido', 'horario invertido', 'sin curso previo', 'grupo no detectado').
- [x] Alcance honesto: PDF DIGITAL (texto); un escaneo de imagen → 0 bloques → el endpoint responde 422 con explicación (OCR de imagen FUERA de alcance, PLAN §7). Tope 10 MB.
- [x] `routers/courses.py`: `POST /courses/import-pdf` (multipart, SOLO admin) devuelve la previsualización editable SIN persistir nada; `POST /courses/import-pdf/confirm` crea cursos faltantes + un grupo por (curso, group_code) + bloques con la MISMA validación RF-06 — **todo o nada** (`add_block(commit=False)` + rollback en excepción).
- [x] Tests `test_ocr_schedule.py` (7): extractor puro (2 cursos, horas pegadas, grupo B), ambiguos (día raro, rango invertido), PDF escaneado, preview rechaza docente (403), preview+confirm E2E (cursos/grupos/bloques en BD), choque → 409 y ROLLBACK completo, escaneo/ilegible/vacío → 422. **67/67 en la suite.**
- **Entregable VERIFICADO E2E:** PDF simulado (reportlab) subido por curl multipart a uvicorn real → preview JSON con 4 bloques confiables → confirm 201 con curso+grupo+2 bloques creados (y eliminados después para dejar la BD demo limpia).

**Lecciones del bloque:**
1. `bool(and )` explícito: `'A' and True` devuelve el STRING 'A' y pydantic lo rechaza como bool (`bool_parsing`).
2. Regex de días GENÉRICO (3-4 letras) + diccionario: lo no reconocido sale ambiguo en vez de perderse silenciosamente.
3. `File(...)` en default de parámetro dispara B008 de ruff: es el patrón estándar de FastAPI, se marca con noqa (o Annotated).
4. La importación masiva necesita `add_block(commit=False)`: el commit propio del servicio rompía el todo-o-nada.

### Bloque 6b - Ampliaciones de asistencia y seguridad (inicio de F3) - **✅ COMPLETADO Y VERIFICADO**
- [x] `GET /attendance/sessions-today` (F3, frontend lo consume): sesiones ABIERTAS de hoy con aula/curso/grupo/docente/bloque; docente solo ve SUS grupos, admin todas; las CERRADAS se excluyen (su corrección es por rectificación RF-15). Test E2E: apertura → aparece, cierre → desaparece.
- [x] **Rate limit de login en el backend** (antes solo en el cliente `auth-rate-limit.ts`): 5 intentos fallidos por IP/minuto con ventana móvil (dict en memoria, mismo patrón que el OTP RF-12), 6º intento → 429 aunque la clave sea correcta; login exitoso limpia la ventana. Tests: bloqueo + reinicio en login correcto; fixture autouse resetea el contador entre tests.
- [x] **`GET /attendance/me`** (nuevo alcance, ver la decisión revisada abajo): historial de asistencias del ESTUDIANTE autenticado (solo rol estudiante; admin/docente → 403), con filtros `?desde=&hasta=` (rango de fechas de sesión) y limit 500. Devuelve record_id, session_date, franja bloque, curso, grupo, estado, marked_at, method y correct_reason (RF-15 visible para el alumno).
- **Decisiones revisadas:**
1. ~~"El rol ESTUDIANTE no entra al panel"~~ → **REVISADO: el estudiante SÍ entra a la app** con su vista personal "Mis asistencias" alimentada por `GET /attendance/me` (el resto del panel sigue restringido a admin/docente). Las alertas por correo (RF-24) se mantienen igual.
- **Entregable VERIFICADO:** 72/72 tests incluyendo los nuevos (sessions-today + rate limit + /attendance/me).

### Bloque 11 - Reglas de negocio (11.1–11.9) - R1…R15 - **✅ COMPLETADO Y VERIFICADO (2026-10-11)**

> Complemento de los bloques 1-9 y 6b. Este bloque nació como documento aparte
> ("REGLAS DE NEGOCIO") y quedó **unificado aquí**: semestre, cupos,
> justificaciones, DPI con aviso único, seguridad y reportes.

**Decisiones confirmadas por el usuario (2026-10-11):**

| # | Tema | Decisión |
|---|---|---|
| 1 | Tardanza (RF-23) | *Asistió*: de `inicio − apertura anticipada` a `inicio + tolerancia`. *Tardanza*: después de eso y hasta el **fin del bloque**. *Falta*: no marcó antes del fin. Llegar **55 min tarde a un bloque de 1 h es tardanza, no falta**. |
| 2 | Límite de inasistencia | 30 %, y la inhabilitación aplica **al SUPERARLO** (> 30 %), no al alcanzarlo. Las tardanzas no suman; las faltas justificadas no cuentan. Aviso preventivo ≥ 20 %. |
| 3 | Quién justifica | Docente (solo sus grupos y su curso) o admin (todos). Todo queda en `audit_log`. Sin plazo para justificar. |
| 4 | Bloques | Solo 1 h o 2 h; cada bloque es una sesión independiente (sin lógica de arrastre). `block_minutes` pasa a ser **informativo** (la duración real sale de `start_time/end_time`). |
| 5 | Grupos | Los crea el admin al llenarse el cupo; cada uno con docente y aula propios. |
| 6 | Cupo | **40 para todos los cursos** (editable por grupo). |
| 7 | Cambio de grupo | Las faltas anteriores se **conservan y se suman al curso** (transferencia = retirar origen + matricular destino en una transacción). |
| 8 | Fechas del semestre | **2026-II: 2026-08-17 → 2026-12-19** (propuesta cargada en `app_settings`); el admin las registra/modifica con `PATCH /settings`. |
| 9 | Escuela / aula | Una sola escuela (sin campo "escuela"); el aula pertenece al grupo, no al bloque; **no** se implementa cambio de aula por fecha. |

**Base de datos (scripts manuales, §1; ejecutados en este orden y verificados):**
1. `db/005_reglas_negocio.sql` — zona horaria `America/Lima` de la BD; `course_group.semester_label` + `capacity` (UNIQUE por semestre); parámetros nuevos (`semester_start/end`, `early_open_minutes` 15, `rectify_days` 7, `dpi_min_sessions` 4, aviso 20/límite 30); `attendance_session.needs_review/cancel_reason/cancelled_by/cancelled_at`; `attendance_record.is_justified/justification_id` (CHECK: justificada ⇒ falta); `enrollment.withdrawn_at`; `app_user.face_consent_at` + CHECK NOT VALID de DNI/WhatsApp; `room.capacity`; tabla `dpi_alert_sent`.
2. `db/006_session_cancelada.sql` — valor `cancelada` del enum `session_status` (archivo aparte: `ADD VALUE` no puede usarse en la misma transacción).
3. `db/007_vistas_reglas.sql` — recrea `v_student_dpi` (semestre vigente, rango de matrícula, justificadas aparte, canceladas y needs_review fuera) y amplía `v_today_attendance` (+`is_justified`, `session_id`, franja, `correct_reason`, `teacher_id`; excluye canceladas).

> **Nota de compatibilidad:** los valores por defecto de `001_schema.sql`
> (`dpi_alert_percent` 30 / `dpi_limit_percent` 33.33) quedan **reemplazados por
> 20/30** vía `005`; `block_minutes` pasa a ser informativo (la duración real
> sale de `start_time/end_time` de cada bloque). `001` y `002` no se editan nunca.

**Reglas y dónde viven (implementado):**

| Id | Regla | Implementación |
|---|---|---|
| R1 Semestre | Grupos con `semester_label`; solo el vigente abre sesiones/valida choques; cambiar de semestre no borra nada | `services/settings.py`, `attendance_engine`, `services/schedule.py`, `courses.py` |
| R2 Ventana | `clasificar()` con la tabla del ejemplo (07:44 · 07:45-08:10 · 08:11-10:00 · 10:01) | `attendance_engine.clasificar` |
| R3 Apertura | El scheduler abre la sesión al iniciar la ventana (sin cámara); `resolver_sesion` solo la localiza (respaldo si nadie la abrió) | `abrir_sesiones_del_dia`, `resolver_sesion` |
| R4 Cierre | Cierra al `fin` (máx. 60 s después); cero marcas → `needs_review` sin faltas; con marcas → faltas a matriculados activos | `cerrar_sesion`, `cerrar_sesiones_pendientes`, `resolver_revision` |
| R5 Cancelación | `cancelada` con motivo y actor; docente (abiertas/por revisar de sus grupos) o admin (también cerradas); `cancel-day` admite fecha futura (crea la sesión cancelada) | `cancelar_sesion`, `cancelar_dia` |
| R6 Justificación | `is_justified` + `justification_id`; crear marca faltas existentes y las futuras nacen justificadas; eliminar revierte; docente con curso obligatorio | `services/justifications.py`, `justificacion_vigente` |
| R7 DPI | `absence_percent` = faltas no justificadas / sesiones válidas; aviso ≥ 20, límite > 30; correo solo con `sessions_held ≥ 4` y **una vez por nivel** (`dpi_alert_sent`); "faltas restantes" contra el total planificado | `services/dpi.py`, `v_student_dpi`, `notifications.py` |
| R8 Matrícula | Cupo 40; un grupo activo por curso; sin cruces de horario del alumno; retiro con `withdrawn_at` (o DELETE si no hay registros); transferencia transaccional | `services/enrollments.py`, `courses.py` |
| R9 Grupos | UNIQUE(course, group_code, semester); cupo por grupo; validación de cruce de los alumnos al crear/editar bloques | `courses.py`, `services/schedule.py` |
| R10 Contiguos | Candidatos por aula+ventana; desempate por la matrícula del alumno reconocido y, si persiste, el bloque que empezó más tarde | `bloques_candidatos`, `resolver_sesion`, `camera_loop` |
| R11 Rectificación | Docente solo últimos `rectify_days` (7); admin sin plazo; motivo obligatorio → `audit_log`; cambiar de falta limpia la justificación | `attendance.py` (`/rectify`) |
| R12 Feriados | Alta por rango (omite fines de semana) y generador nacional (fijos + Semana Santa); al crear un feriado se cancelan las sesiones abiertas/por revisar de esa fecha | `calendar_admin.py`, `services/holidays_pe.py` |
| R13 Biometría | Consentimiento obligatorio (`face_consent_at`); `DELETE /students/{id}/faces` borra embeddings y foto; galería solo con usuarios activos | `services/faces.py`, `enrollment_faces.py`, `ai/runtime.py` |
| R14 Seguridad | Con `must_change_password` todo 403 (`code: must_change_password`) salvo `/auth/me` y `/auth/change-password`; `is_active` verificado por request; `rtsp_url` enmascarada en listados (y un PATCH con `***` se ignora) | `core/deps.py`, `catalog.py` |
| R15 Formatos Perú | DNI 8 dígitos; WhatsApp 9 empezando en 9; correo `@unamba.edu.pe` configurable (`ALLOWED_EMAIL_DOMAIN`, vacío = sin validar; admin exento) | `services/formats.py`, `.env.example` |

**Endpoints nuevos/modificados (resumen):** `POST /sessions/{id}/cancel` · `POST /blocks/{id}/cancel-day` (`fecha` opcional) · `GET /attendance/sessions-review` · `POST /sessions/{id}/resolve-review` · `PATCH /attendance/{id}/justify` · `GET/POST/DELETE /justifications` (docente con efecto) · `PATCH /attendance/{id}/rectify` (plazo) · `POST /groups/{id}/students` + `DELETE` + `POST …/transfer` (R8) · `GET /courses/{id}/groups` (`semester`, `capacity`, `enrolled_count`) · `GET /settings/semesters` · `GET /dpi/at-risk` · `GET /students/{id}/dpi` · `GET /attendance/me/dpi` · `POST /holidays/range` · `POST /holidays/national?year=` · `POST`/`DELETE /students/{id}/faces` (`consent`) · `GET /devices/{id}` · `GET /reports/group-matrix.xlsx?group_id=` · `GET /reports/dpi-risk.xlsx?course_id=` · `GET /audit-log` (+`actor_role`) · `GET /dashboard/summary` (+`en_riesgo`, `sessions_to_review`, filtro por docente).

**Tests (11.9) — nuevos archivos:** `test_rules_window.py` (R2 y niveles DPI puros), `test_sessions_lifecycle.py` (R3/R4/R5/R10), `test_justifications.py` (R6/R11 + permisos), `test_enrollment_rules.py` (R8/R9), `test_dpi.py` (R7 + envío único + semestre), `test_security.py` (R13/R14). Los tests existentes se actualizaron a la nueva regla (tardanza R2, cierre con needs_review, consentimiento) y `helpers_b6` ahora crea grupos con el semestre vigente y limpia justificaciones/auditoría.

**Fuera de alcance (se documenta como limitación):** detección de vida (anti-foto), multi-escuela/multi-sede, cambio de aula por fecha, panel completo de periodos académicos (basta etiqueta + fechas), subida de documentos de justificación (se mantiene `document_url` como enlace) y reasignación de docente con historial separado.

### Bloque 10 - Calidad y demo final (1–2 días) - **se ejecuta DESPUÉS del Bloque 11**
- [ ] Tests pytest (`fareas_test`); motor y auth con prioridad.
- [ ] Producción simple: `fastapi run` + Cloudflare Tunnel; el build de Angular se sirve desde el propio FastAPI con `app.frontend("dist/fareas/browser")` (un solo origen, sin CORS).
- [ ] README final con diagrama, protocolo ESP32 y guion de demo de tesis.
- **Entregable:** demo end-to-end: PDF → matrícula → enrolamiento → video/entrada real → asistencia → reportes.

---

## 4. Dispositivos REALES que tienes (cámara, ESP32, LED, buzzer)

### 4.1 Cámara Hikvision PoE (RF-17)
1. **Conexión física:** cámara → puerto PoE+ del TP-Link LS108GP con cable Cat6 (un solo cable: datos + energía).
2. **Descubrir su IP:** herramienta **SADP** de Hikvision (Windows). La cámara viene por defecto en `192.168.1.64` con usuario `admin` y contraseña que se define al activarla (guárdala).
3. **IP fija:** desde SADP o la web de la cámara, pon una IP del rango de tu red, p. ej. `10.14.5.11` (coincide con el seed).
4. **URL RTSP** (la que va en `device.rtsp_url`):
   - Stream principal: `rtsp://admin:CONTRASEÑA@10.14.5.11:554/Streaming/Channels/101`
   - **Sub-stream (RECOMENDADO para el pipeline: menos CPU):** `.../Channels/102` (~640×480).
5. **Probar sin backend:** `python scripts/test_rtsp.py` (lo creo en el Bloque 5) - abre el stream y muestra 1 frame.
6. Registro en BD: `UPDATE device SET rtsp_url='...', ip_address='...' WHERE device_key='cam-lab305';` (yo lo hago cuando me pases IP/contraseña).

### 4.2 ESP32 + anillo NeoPixel WS2812B + buzzer (RF-25, RF-27…RF-29, RF-33)
- **Cableado:**
  - Anillo NeoPixel (16 LEDs): `VCC→5V` (USB del ESP32), `GND→GND`, `DATA→GPIO 13` con **resistencia 330–470 Ω** en serie y un condensador 1000 µF entre 5V y GND (buena práctica).
  - Buzzer activo 5V: `+→GPIO 26` (**⚠️ actualizado en el Bloque 11: era GPIO 12, que es pin de arranque del ESP32 y colgaba el boot**; para un buzzer pequeño de 3.3 V puede ser directo; si es de 5 V real, usa un transistor NPN 2N2222 con resistencia de base 1 kΩ) y `−→GND`.
  - **Firmware (corrección Bloque 11):** el `hello` se envía en el evento `WStype_CONNECTED` (no en `setup()`), y se reserva **IP fija (DHCP)** para la PC del backend; el ESP32 solo usa WiFi de 2.4 GHz.
- **Firmware (Arduino IDE):** librerías `WiFi.h`, `WebSocketsClient` (Links2004) y `Adafruit_NeoPixel`.
  - Conecta a `ws://IP-DE-TU-PC:8000/api/v1/ws/devices?token=<DEVICE_TOKEN_SECRET del .env>`.
  - Envía `{"type":"hello","device_id":"esp32-lab305"}` (**debe coincidir con `device.device_key`** de la BD) y `{"type":"heartbeat"}` cada 30 s.
  - Interpreta los comandos `verdict`: color y beeps según la Tabla 8 (verde+1 beep / amarillo+2 beeps / rojo+tono sostenido / azul animación en reposo).
- **Red:** el ESP32 y tu PC deben estar en la misma LAN (router del aula) y el **firewall de Windows debe permitir el puerto 8000** (avísame y te preparo el comando exacto con permiso).
- **Simulador primero:** `scripts/simulate_esp32.py` prueba todo el protocolo desde la PC antes de tocar el hardware.

### 4.3 Orden recomendado de integración con hardware
1. Bloque 5 con MP4 (sin cámara) → 2. cámara real con `test_rtsp.py` → 3. Bloque 7 con `simulate_esp32.py` → 4. ESP32 físico → 5. puerta real del aula.

---

## 5. Mapeo dashboard.html ↔ endpoints (Bloque 8)

| Widget actual (mock) | Endpoint |
|---|---|
| Tarjeta "Asistencias hoy" (128 / 12 tardanzas) | `GET /api/v1/dashboard/summary` |
| Tarjeta "Ausencias" (11 / 7.7 %) | `GET /api/v1/dashboard/summary` |
| Tarjeta "Cámaras activas" (14/16, streams caídos) | `GET /api/v1/dashboard/summary` (detalle: `GET /devices/status`, RF-35) |
| Tarjeta "Alertas críticas DPI" (**R7: alerta ≥ 20 %, límite > 30 %**) | `GET /api/v1/dashboard/summary` (fuente: vista `v_student_dpi`; añade `en_riesgo` y `sessions_to_review`; con rol docente todo va filtrado por sus grupos) |
| `app-activity-feed` (EN VIVO, similitud, veredicto) | `GET /api/v1/dashboard/live` - SSE (`EventSourceResponse`) |
| `app-student-list` (estudiante, estado, curso, aula, hora) | `GET /api/v1/attendance/today?course=&group=&room=` (vista `v_today_attendance`) |
| `app-hourly-chart` (asistencia por hora 07–20) | `GET /api/v1/stats/hourly?day=YYYY-MM-DD` |
| `app-distribution-chart` (dona Asistió/Tardanza/Sin registro/Falta) | `GET /api/v1/stats/distribution?from=&to=` |

Convención única de estados en todo el sistema: `asistio | tardanza | falta | sin_registro` (RF-23) y veredictos de puerta según la Tabla 8.

---

## 6. Tareas que requiere hacer TÚ (avísame cuando las hagas)

1. **Cuando probemos la cámara real:** pasarme la IP fija y contraseña RTSP (o ejecutar tú el `test_rtsp.py` y pegarme la salida).
2. **Cuando probemos el ESP32 real:** abrir el puerto 8000 del firewall de Windows (te preparo el comando y me das permiso para ejecutarlo).

---

## 8. Cronograma restante

| Semana | Bloques | Hito |
|---|---|---|
| 1 | ~~1, 3~~ ✅ | ~~App bajo app/main.py + login JWT~~ - COMPLETADO |
| 2 | ~~4, 5~~ ✅ | ~~Malla académica + reconocimiento funcionando con video/MP4~~ - COMPLETADO |
| 3 | ~~6, 7~~ ✅ | ~~Motor de asistencia + protocolo ESP32~~ — COMPLETADO (el ESP32 físico se conecta cuando lo armes) |
| 4 | ~~8, 9~~ ✅ | ~~Dashboard + reportes + OCR~~ — COMPLETADO |
| 5 | **11 (reglas de negocio)** ✅ | Semestre, cupos, transferencias, justificaciones, DPI con aviso único, seguridad y reportes por grupo — COMPLETADO (ver §3, Bloque 11) |
| 6 | 10 | Calidad y demo final (README, demo E2E, tunnel) |
