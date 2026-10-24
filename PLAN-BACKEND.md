# PLAN DE IMPLEMENTACIÓN - BACKEND FAREAS (Angular + FastAPI + PostgreSQL 17)

> Proyecto académico: Control de asistencia con reconocimiento facial - Facultad de Informática, UNAMBA.
> Principio rector: **profesional y técnico, no empresarial**. Un monolito modular en FastAPI. Sin Redis, sin Celery, sin workers externos, **sin Alembic**, **sin pgvector**, **sin Docker**. Cada bloque termina con algo ejecutable y verificable.

---

## 0. Estado actual (progreso ya completado y verificado)

| ✅ Hecho | Detalle |
|---|---|
| Base de datos creada | PostgreSQL **17.11** (instalador oficial Windows). BD `fareas` creada y migrada |
| Esquema completo | `back-fareas/db/001_schema.sql` ejecutado: 15 tablas, 4 enums, vistas `v_today_attendance` y `v_student_dpi` |
| Datos demo cargados | `back-fareas/db/002_seed.sql`: 1 admin + 2 docentes + 6 estudiantes, 6 aulas, 12 dispositivos, 6 cursos (ISA901…ISA906), 16 bloques horarios, 36 matrículas |
| Modelos ONNX en su sitio | `back-fareas/models/`: `det_10g.onnx` (17 MB, SCRFD) + `w600k_r50.onnx` (174 MB, ArcFace 512-d) - copiados desde tus descargas |
| Stack instalado | SQLModel, asyncpg, APScheduler, opencv-python 4.10, onnxruntime 1.20, numpy 2.1, openpyxl, reportlab, pdfplumber - todos importan OK en el venv |
| Modelos probados | Ambos `.onnx` cargan en CPU (0.1 s / 0.3 s); ArcFace salida confirmada: vector **[1, 512]** |
| Búsqueda vectorial validada | Benchmark NumPy: **0.23 ms** por búsqueda contra 5000 alumnos (la opción sin pgvector sobra para la facultad) |
| Configuración | `.env` con `postgresql+asyncpg://postgres:***@localhost:5432/fareas`, JWT, SMTP, umbral facial 0.75, `DEVICE_TOKEN_SECRET` |
| Almacenamiento R2 | Bucket `fareas-assets` (WNAM, privado) creado. Variables `R2_*` en `.env`/`.env.example` y en `Settings`; credenciales cargadas en el `.env` local. `services/storage.py`, la portada del enrolamiento y el adjunto de justificación suben a R2 con URL firmada (Bloque 13 completado) |
| **Bloque 1 completado** | `app/main.py` + `pyproject.toml` (entrypoint `fastapi dev`), `database.py` (SQLModel async), `core/deps.py`, `tables.py` (14 entidades SQLModel con enums nativos), scripts `test_rtsp.py` y `simulate_esp32.py`. Verificado con servidor uvicorn real: `GET /api/v1/health` → `{"database":"ok","users":9}`. Ruff limpio |
| **Cambio de contraseña con OTP (2026-10-22)** | Flujo de 3 pasos (`/auth/change-password/otp` → `/otp/verify` → `/change-password`), servicio `services/otp.py` con propósito + cooldown/TTL/intentos, `token_version` para invalidar JWT (columna ya consolidada en `001`). Suite: **92 passed** (sin `test_vision.py`) |
| **OCR de fotos y nómina (2026-10-22)** | Bloques 14/15 implementados: horario desde PDF escaneado o foto con RapidOCR, periodo/ciclo, docente/aula por fila e importación idempotente; nómina de alumnos con preview editable, correo generado y confirmación fila por fila. Suite: **122 passed** (sin `test_vision.py`) |
| **Notificaciones por rol (2026-10-23)** | Tabla `notification`, bandeja en el sistema con contador y cola de correo con reintentos; avisos de DPI, justificaciones, cancelaciones, revisiones, rectificaciones y dispositivos. Suite: **178 passed** (sin `test_vision.py`) |

### Decisiones definitivas

1. **Sin pgvector** - embeddings en columna `REAL[512]`; similitud coseno en NumPy (0.23 ms medidos). El archivo `requirements.txt` **ya no incluye pgvector** ✔. El SQL que se genera en el futuro (migraciones manuales) tampoco lo requiere.
2. **Sin Alembic** - la BD se crea/actualiza con **scripts SQL manuales numerados** en `back-fareas/db/` que tú ejecutas en pgAdmin o psql. Detalle en §1.
3. **Sin Docker** - todo nativo en Windows: PostgreSQL (instalador oficial), Python en `.venv`, OpenCV/ONNX Runtime vía pip. Docker queda descartado para este proyecto.
4. **No se entrena ningún modelo** - pesos preentrenados buffalo_l; el "aprendizaje" del sistema es el enrolamiento (RF-04).
5. **No comentarios en el código** - no incluir comentarios salvo que sean estrictamente necesarios para explicar una lógica compleja. El código debe ser autoexplicativo (nombres claros, funciones pequeñas).
6. **Código en inglés desde ahora** - los identificadores nuevos (funciones, variables, clases, parámetros, archivos y tests) deben escribirse en inglés. Los textos visibles al usuario, los mensajes de error de la API, los valores de dominio existentes y la documentación pueden permanecer en español. No se renombra código existente dentro de features nuevas; cualquier normalización se hace en un refactor aparte.

---

## 1. Gestión de la base de datos sin migraciones automáticas

```
back-fareas/db/
├── 001_schema.sql    # esquema completo y vigente (se corre sobre BD vacía)
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
├── storage/                        # fotos locales de desarrollo/pruebas; producción en R2 (Bloque 13) - gitignored
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
│   │   ├── ocr_extract.py          # PDF texto/escaneado o foto → líneas con coordenadas
│   │   ├── ocr_schedule.py         # RF-07: regex sobre las líneas del horario
│   │   ├── ocr_roster.py           # nómina impresa → alumnos con columnas
│   │   ├── students_import.py      # preview y alta masiva fila por fila
│   │   └── storage.py              # Bloque 13: R2 (boto3) + URLs firmadas
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
- [x] `core/security.py`: argon2 (pwdlib, formato PHC igual al seed) + JWT HS256 (`sub`, `role`, `ver`, 120 min).
- [x] `routers/auth.py`: `POST /auth/login` (por email **o** código de matrícula), `GET /auth/me`, `POST /auth/change-password` (apaga `must_change_password`, RF-11), `POST /auth/recover` + `/verify` + `/reset` (OTP 6 dígitos, TTL 10 min, máx. 5 intentos, respuesta uniforme que no revela si el correo existe - RF-12). **2026-10-22:** cambio voluntario con OTP (`/change-password/otp` + `/otp/verify`) y `token_version`.
- [x] `core/deps.py`: `CurrentUser` (Bearer), `CurrentUserPending` (R14) y `RequireRole(...)` para los routers del Bloque 4 (RF-01). Verifica `ver` contra `app_user.token_version`.
- [x] `services/emailer.py`: aiosmtplib con `MAIL_ENABLED=false` en desarrollo (registra el contenido sin enviar; ⚠️ rota la clave del Gmail, §6). OTP con propósito (`recover`/`change_password`) y aviso de contraseña actualizada.
- [x] `tests/test_auth.py`: **12/12 tests** contra la BD `fareas` real (login, /me, cambio forzado, cambio voluntario con OTP, cooldown, expiración, máximo de intentos, invalidación de token, recuperación completa, reset sin verificar OTP rechazado), con usuario temporal creado y limpiado por fixtures.

**Lecciones del bloque (documentadas para los siguientes):**
1. Las columnas `DEFAULT NOW()` deben declararse con `server_default=text("now()")` en `tables.py`, o el ORM envía NULL explícito y viola el NOT NULL (pisaría el default de la BD).
2. En pruebas, TODO en un solo event loop: `httpx.AsyncClient` + `ASGITransport`. Mezclar `TestClient` con sesiones del pool en otro loop corrompe asyncpg (`Event loop is closed`); el engine se hace `dispose()` tras cada test (fixture autouse).

- **Entregable:** login de los 3 roles contra la BD verificado con servidor uvicorn real (token JWT emitido y `/auth/me` respondiendo) ✔

### Bloque 3b - Cambio de contraseña con OTP (2026-10-22) - **✅ COMPLETADO Y VERIFICADO**
> Objetivo: cambiar la clave desde "Mi perfil" sin depender de un enlace, usando
> el correo institucional como segundo factor. Todos los roles usan el mismo flujo.

**Flujo (RF-11 + RF-12):**
1. `POST /auth/change-password/otp` `{current_password}` — valida la clave actual,
   aplica cooldown de 60 s y envía un OTP de 6 dígitos. Devuelve el correo
   enmascarado (`ju*****ez@unamba.edu.pe`), `expires_in=600` y `resend_in=60`.
2. `POST /auth/change-password/otp/verify` `{code}` — valida el código y lo marca
   `verified`. Un código incorrecto consume un intento (máx. 5).
3. `POST /auth/change-password` `{current_password, new_password}` — exige el OTP
   verificado, lo **consume** (un solo uso) y actualiza la contraseña.

**Decisiones clave:**
- El OTP **no reemplaza** la contraseña actual: la petición final vuelve a exigirla.
- La clave temporal (`must_change_password=true`) se cambia **sin OTP** en el
  primer login (el usuario acaba de recibirla y el guard lo obliga a cambiarla).
- `services/otp.py` centraliza TTL (10 min), cooldown (60 s), máximo de intentos
  (5), hash argon2id del código y binding por `(user_id, purpose)`; el store es
  la tabla `password_otp` (UNIQUE por usuario y propósito), sin Redis. Las sesiones usan
  refresh tokens (`refresh_token`, 30 días, rotación por familia) y el frontend renueva el
  access token ante un 401.
- `app_user.token_version` (`INTEGER NOT NULL DEFAULT 0`) viaja como claim `ver`.
  Al cambiar/restablecer se incrementa: los JWT viejos responden 401 y la
  respuesta entrega un `access_token` nuevo; el frontend lo persiste para no
  perder la sesión actual.
- Se audita `password_change_otp`, `password_changed` y `password_reset` (RF-32)
  y se envía `send_password_changed_notice` al correo institucional.

**BD:** `db/001_schema.sql` actualizado (columna `token_version`); el ALTER
correspondiente ya se consolidó y se borró tras aplicarse a la BD local `fareas`.

**Tests:** `tests/test_auth.py` (12/12) cubre el flujo voluntario completo,
cooldown, expiración, máximo de intentos, OTP incorrecto, consumo único, token
viejo inválido, token nuevo válido, cambio forzado sin OTP y recuperación
completa; `tests/test_security.py` usa el token nuevo tras el cambio. Suite
completa sin `test_vision.py`: **92 passed**.

### Bloque 4 - Catálogo académico (1–2 días) - RF-02…RF-06, RF-09, RF-10, RF-32, RF-34, RF-35 - **✅ COMPLETADO Y VERIFICADO**
- [x] CRUDs de aulas (`/rooms`), dispositivos (`/devices`, `/devices/status` público RF-35), docentes (`/teachers`) y estudiantes (`/students`), con paginación (`?page=&page_size=&q=`).
- [x] RF-08: alta de docente/estudiante genera **clave temporal** y la envía por correo (`services/accounts.py`); `POST /accounts/{id}/send-temp-password` la reenvía con clave nueva.
- [x] Cursos → grupos → bloques con **validación de solapamientos** en `services/schedule.py`: rechaza mismo aula o mismo docente en rangos que se cruzan; grupos paralelos (aula y docente distintos) SÍ se permiten (Tabla 2). **R9 (2026-10-16):** el AULA es del bloque (`schedule_block.room_id`, obligatoria); el choque se compara contra el aula del bloque y la semana lectiva es **Lun–Vie** (CHECK `weekday BETWEEN 1 AND 5`). **R9 (2026-10-17):** se eliminó `course_group.room_id` (la «aula sugerida»); el grupo ya no lleva aula y un bloque sin `room_id` responde **422** («Indica el aula donde se dicta el bloque») en `services/schedule.py` (`db/004_aula_solo_en_bloque.sql`). Nuevo `GET /schedule`: la semana completa de un semestre (join bloque+grupo+curso+docente+aula, filtros `course_id`/`teacher_id`/`room_id`, `include_inactive`) para la vista general de horarios. **RF-01 (2026-10-16):** todo bloque cae dentro de la franja de clases de `app_settings` (`attendance_hour_start/end`, 07:00–20:00) al crear y al editar → 422 con el motivo; la baja del grupo es lógica y se deshace con `POST /groups/{id}/activate` (auditado).
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
- [x] `routers/enrollment_faces.py` + `services/faces.py`: 3–5 fotos base64 → exige exactamente 1 rostro por foto, consistencia intra-alumno (cada foto frente al promedio de las demás ≥ 0.40; antes se exigía 0.55 entre todos los pares y rechazaba a una misma persona con poses distintas: medido con el video demo, solo el 13 % de los grupos de 3–5 fotos pasaba, frente al 99 % con la regla nueva), PROMEDIO normalizado a `face_embedding` (`REAL[512]`), portada en `storage/`, reemplazo del embedding anterior (`is_current`), auditoría RF-32 y recarga de galería en caliente.
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
- [x] Alcance honesto: PDF DIGITAL (texto); un escaneo de imagen → 0 bloques → el endpoint responde 422 con explicación (OCR de imagen FUERA de alcance, PLAN §7). Tope 10 MB. **→ Superado por el Bloque 14:** las fotos y los PDF escaneados se leen con RapidOCR; el PDF digital sigue por la vía de texto (más rápida y exacta).

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
| 5 | Grupos | Los crea el admin al llenarse el cupo; cada uno con su docente (el aula se elige en cada bloque). |
| 6 | Cupo | **40 para todos los cursos** (editable por grupo). |
| 7 | Cambio de grupo | Las faltas anteriores se **conservan y se suman al curso** (transferencia = retirar origen + matricular destino en una transacción). |
| 8 | Fechas del semestre | **2026-II: 2026-08-17 → 2026-12-19** (propuesta cargada en `app_settings`); el admin las registra/modifica con `PATCH /settings`. |
| 9 | Escuela / aula | Una sola escuela (sin campo "escuela"); el aula pertenece al **BLOQUE**, no al grupo, para que un mismo grupo dicte en laboratorios distintos según el día. **(2026-10-16, 003_aula_por_bloque.sql; 2026-10-17 se quitó del todo `course_group.room_id`, 004_aula_solo_en_bloque.sql.)** |

**Base de datos (scripts manuales, §1; verificados):**
1. `db/001_schema.sql` — **esquema completo y vigente** (absorbe lo que se aplicó
   en los ya borrados `005`/`006`/`007`): zona horaria `America/Lima` de la BD;
   `course_group.semester_label` + `capacity` (UNIQUE por semestre); parámetros
   nuevos (`semester_start/end`, `early_open_minutes` 15, `rectify_days` 7,
   `dpi_min_sessions` 4, aviso 20/límite 30);
   `attendance_session.needs_review/cancel_reason/cancelled_by/cancelled_at`;
   `attendance_record.is_justified/justification_id` (CHECK: justificada ⇒
   falta); `enrollment.withdrawn_at`; `app_user.face_consent_at` + CHECK NOT
   VALID de DNI/WhatsApp; `room.capacity`; tabla `dpi_alert_sent`; valor
   `cancelada` del enum `session_status`; vistas `v_student_dpi` y
   `v_today_attendance` con las reglas R5/R6/R7;
   `course.cycle SMALLINT NOT NULL` (CHECK 1–10, ciclo de la malla).
2. `db/002_seed.sql` — datos demo + los parámetros vigentes del semestre
   (umbral facial calibrado 0.55, DPI 20/30, semestre 2026-II). El horario demo
   lleva **el aula en cada bloque** y no puede tener clases cruzadas para un
   alumno: R8c/R9 lo rechazaría al editar (por eso ISA901 iba Vie 07:00-09:00).
   Los 6 cursos ISA901–ISA906 se siembran en el **ciclo 9**.
3. `course.cycle` (ciclo 1–10 con CHECK) ya está consolidado en `001`/`002`; el ALTER
   `003_ciclo_curso.sql` se aplicó y se borró. Las antiguas migraciones de aula
   (`003_aula_por_bloque`, `004_aula_solo_en_bloque`) también se consolidaron; los
   ALTER se borran cuando todo el equipo los aplicó (regla en el README).

> **Nota de compatibilidad (regla vigente, 2026-10-16):** `001_schema.sql` **sí
> se edita**: es la foto del esquema real, y `002_seed.sql` fija los valores
> vigentes. Un cambio de BD = ALTER nuevo (`003_…` para las BD ya existentes) +
> `001`/`002` actualizados en el mismo commit + borrado del ALTER que ya aplicó
> todo el equipo. Así una BD nueva **o vieja** se pone al día con 2 scripts
> (detalle en `back-fareas/README.md` >> "Actualizaciones de la base de datos").
> `block_minutes` es informativo: la duración real sale de `start_time/end_time`.

**Reglas y dónde viven (implementado):**

| Id | Regla | Implementación |
|---|---|---|
| R1 Semestre | Grupos con `semester_label`; solo el vigente abre sesiones; cambiar de semestre no borra nada. El **ciclo** (`course.cycle`, 1–10) separa los horarios dentro del mismo periodo; los choques se validan entre todos los ciclos del periodo | `services/settings.py`, `attendance_engine`, `services/schedule.py`, `courses.py` |
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
| R13 Biometría | Consentimiento obligatorio (`face_consent_at`); `DELETE /students/{id}/faces` borra embeddings y objeto (local o R2); galería solo con usuarios activos | `services/faces.py`, `enrollment_faces.py`, `ai/runtime.py` |
| R14 Seguridad | Con `must_change_password` todo 403 (`code: must_change_password`) salvo `/auth/me` y `/auth/change-password`; `is_active` verificado por request; `rtsp_url` enmascarada en listados (y un PATCH con `***` se ignora) | `core/deps.py`, `catalog.py` |
| R15 Formatos Perú | DNI 8 dígitos; WhatsApp 9 empezando en 9; correo `@unamba.edu.pe` configurable (`ALLOWED_EMAIL_DOMAIN`, vacío = sin validar; admin exento) | `services/formats.py`, `.env.example` |

**Endpoints nuevos/modificados (resumen):** `POST /sessions/{id}/cancel` · `POST /blocks/{id}/cancel-day` (`fecha` opcional) · `GET /attendance/sessions-review` · `POST /sessions/{id}/resolve-review` · `PATCH /attendance/{id}/justify` · `GET/POST/DELETE /justifications` (docente con efecto) · `PATCH /attendance/{id}/rectify` (plazo) · `POST /groups/{id}/students` + `DELETE` + `POST …/transfer` (R8) · `GET /courses/{id}/groups` (`semester`, `capacity`, `enrolled_count`) · `GET /settings/semesters` · `GET /dpi/at-risk` · `GET /students/{id}/dpi` · `GET /attendance/me/dpi` · `POST /holidays/range` · `POST /holidays/national?year=` · `POST`/`DELETE /students/{id}/faces` (`consent`) · `GET /devices/{id}` · `GET /reports/group-matrix.xlsx?group_id=` · `GET /reports/dpi-risk.xlsx?course_id=` · `GET /audit-log` (+`actor_role`) · `GET /dashboard/summary` (+`en_riesgo`, `sessions_to_review`, filtro por docente).

**Tests (11.9) — nuevos archivos:** `test_rules_window.py` (R2 y niveles DPI puros), `test_sessions_lifecycle.py` (R3/R4/R5/R10), `test_justifications.py` (R6/R11 + permisos), `test_enrollment_rules.py` (R8/R9), `test_dpi.py` (R7 + envío único + semestre), `test_security.py` (R13/R14). Los tests existentes se actualizaron a la nueva regla (tardanza R2, cierre con needs_review, consentimiento) y `helpers_b6` ahora crea grupos con el semestre vigente y limpia justificaciones/auditoría.

**Fuera de alcance (se documenta como limitación):** detección de vida (anti-foto), multi-escuela/multi-sede, cambio de aula por fecha, panel completo de periodos académicos (se mantiene etiqueta + fechas; el ciclo ya es una dimensión del curso), adjunto de justificación (se implementa en el Bloque 13; `document_url` externo se mantiene como compatibilidad) y reasignación de docente con historial separado.

### Bloque 12 - Horarios por ciclo (2026-10-22) - RF-06 - **✅ COMPLETADO Y VERIFICADO**
> Motivo: en UNAMBA cada periodo general (p. ej. 2026-II) contiene 10 ciclos
> (I–X), cada uno con su propia malla y su propio horario. El modelo solo tenía
> `semester_label` (periodo), así que los cursos de todos los ciclos se
> mezclaban en una única semana.

**Decisión de modelo:** el **periodo** sigue en `course_group.semester_label`
(2026-II) y el **ciclo** se guarda en `course.cycle` (1–10). El grupo hereda el
ciclo de su curso; no se duplica en `course_group`. No se crean 10 periodos:
los choques de aula y docente deben seguir detectándose **entre ciclos** del
mismo periodo.

- [x] BD: `course.cycle SMALLINT NOT NULL CHECK (1–10)` en `001`, seed al ciclo
  9 en `002` y ALTER re-ejecutable `003_ciclo_curso.sql` aplicado a `fareas`.
- [x] `app/tables.py`: `Course.cycle`; `CourseIn`/`CourseOut`, `GroupOut` y
  `ScheduleRowOut` exponen `cycle`; `GET /courses`, `GET /groups` y
  `GET /schedule` aceptan `?cycle=1..10`; la importación PDF recibe `cycle` para
  los cursos nuevos.
- [x] `services/schedule.py`: el chequeo de choques usa el **periodo del grupo**
  (`group.semester_label`) y no el periodo vigente global; así se puede editar
  un horario histórico sin falsos conflictos. El chequeo sigue cubriendo todos
  los ciclos del periodo (no se filtra por ciclo).
- [x] Tests: `tests/test_cycle_schedule.py` (curso/ciclo, filtros, choque entre
  ciclos del mismo periodo y bloque de periodo antiguo sin choque cruzado);
  `test_courses`, `test_ocr_schedule`, `helpers_b6` y `_f3_fixture` actualizados
  con `cycle`. Suite completa: **113 passed**.

**Endpoints:** `GET /courses?cycle=` · `POST /courses {code,name,cycle}` ·
`GET /groups?cycle=` · `GET /schedule?semester=&cycle=` ·
`POST /courses/import-pdf/confirm {...,cycle}`.

### Bloque 13 - Almacenamiento de archivos en Cloudflare R2 (2026-10-22) - RF-04, RF-10, R13 - **✅ COMPLETADO Y VERIFICADO**

> **Decisión: fase separada.** El almacenamiento es transversal (enrolamiento,
> justificaciones, privacidad, borrado y producción), no una pantalla de F4/F6.
> Meterlo dentro de F4 escondería la migración, el servicio, las URLs firmadas y
> las pruebas de regresión. F4 solo consume la API; F8 no recibe credenciales R2.
>
> **Bucket:** `fareas-assets` (WNAM, privado). `R2_ENABLED=true` en `.env`.
> **Bloqueo actual:** faltan `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY`.

**Qué va a R2 y qué no:**

| Sí va a R2 | No va a R2 |
|---|---|
| Portada del enrolamiento: `students/{student_id}/faces/{uuid}.jpg` | Embeddings faciales (`face_embedding.vector`) |
| Adjunto de justificación: `justifications/{justification_id}/{uuid}.{ext}` | PDF de importación de horario: se procesa en memoria y se descarta |
| Futuras imágenes de curso/perfil, si se habilitan | Reportes XLSX/PDF: se generan por request y se descargan |
|  | Importaciones Excel/PDF: se procesan en memoria |

**Diseño acordado:**

- Bucket **privado** + subida desde FastAPI con `boto3` (API S3) + URLs GET
  firmadas de corta duración. El navegador **nunca** recibe credenciales R2 ni
  sube directo; solo consume URLs firmadas de lectura.
- Endpoint S3: `https://<account>.r2.cloudflarestorage.com` (**sin**
  `/fareas-assets`), `R2_REGION=auto`, `R2_BUCKET_NAME=fareas-assets`.
- La BD guarda **claves de objeto**, no URLs públicas. Para no migrar ahora, la
  portada reutiliza `face_embedding.photo_url` como clave R2
  (`students/{student_id}/faces/{uuid}.jpg`); el adjunto de justificación usará
  `justification.document_key` cuando se implemente. `document_url` queda como
  compatibilidad para enlaces externos. Los DTO siguen exponiendo
  `photo_url`/`document_url`, pero ya firmadas.
- `services/storage.py`: `put_object`, `delete_object` y `signed_get_url`.
  `boto3` es síncrono → llamadas con `asyncio.to_thread`; errores del proveedor
  se traducen a 502/503 con mensaje controlado.
- Límites: 5 MB por foto y 10 MB por adjunto. Formatos: JPEG/PNG/PDF; validar
  el contenido real (OpenCV para imágenes, cabecera `%PDF-` para PDF), no solo
  la extensión.
- TTL de URLs firmadas: **900 s** (`R2_PRESIGN_EXPIRE_SECONDS`). No guardar URLs
  firmadas en BD ni en logs; solo claves.
- Borrado: `DELETE /students/{id}/faces` elimina el objeto; eliminar una
  justificación elimina su adjunto. Si la transacción de BD falla después de
  subir, se borra el objeto (compensación).
- **Sin CORS** para el flujo recomendado: la subida pasa por FastAPI y la
  visualización es directa con `<img>`/`<a>` sobre la URL firmada. Si el
  frontend descarga con `fetch`/blob o se habilita subida directa desde el
  navegador, agregar CORS para `http://localhost:4200` y el origen de
  producción (GET/PUT/HEAD, headers `*`, exponer `ETag`).
- No se habilita la **Public Development URL** ni se necesita dominio custom
  para URLs firmadas. Si algún día se quieren URLs públicas, usar otro bucket y
  nunca exponer biometría.

**Tareas:**

- [x] Bucket `fareas-assets`, endpoint y `R2_*` en `.env`/`.env.example` y en
  `core/config.py` (cuenta, bucket, endpoint, región, TTL, límite).
- [x] Credenciales `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` cargadas en el
  `.env` local (no versionado), token limitado al bucket.
- [x] `boto3==1.43.118` en `pyproject.toml` y `requirements.txt`.
- [x] `services/storage.py`: `LocalStorage` (fallback dev/tests),
  `R2Storage` (put/delete/URL firmada con `asyncio.to_thread`) y `face_key`.
  Pruebas con fake en `tests/test_storage.py` (5 tests).
- [x] `services/faces.py` y `enrollment_faces.py`: la portada se sube a R2
  después de validar las fotos, `photo_url` guarda la clave y las respuestas
  entregan la URL firmada; eliminar el rostro borra el objeto.
- [x] README: variables R2, bucket, límites y estado del flujo.
- [x] Migración SQL re-ejecutable `db/009_justificacion_documento.sql` y columna
  `justification.document_key` en `001`/`tables.py`.
- [x] `calendar_admin.py`: `POST /justifications/{id}/document` (multipart, PDF/JPG/PNG
  ≤ 10 MB con validación de firma real, 413/415/503 controlados) y
  `DELETE /justifications/{id}/document`; `document_url` firmada en el listado;
  `document_url` externo se mantiene como compatibilidad. Eliminar la justificación
  borra el objeto; reemplazar el adjunto borra el anterior.
- [x] Verificación E2E con una foto real de enrolamiento desde `/faces`
  (la subida directa contra R2 ya está verificada).
- [x] Tests de adjuntos (`tests/test_justification_documents.py`, 5): subida,
  listado firmado, reemplazo, 415, 413, borrado del documento/justificación y
  docente ajeno (403). Verificado con `LocalStorage`; R2 usa el mismo servicio ya
  probado contra el bucket.

**Entregable:** enrolar un alumno guarda la portada en R2 (no en `storage/`),
la web la muestra con URL firmada, `DELETE` borra el objeto, y una justificación
con adjunto se sube/descarga/elimina sin exponer el bucket.

**Verificación real (2026-10-22):** `PUT`/`GET` firmado/`DELETE` contra R2
`fareas-assets` OK con `_smoke/fareas-upload-test.txt` y con
`students/9999/faces/<uuid>.jpg` (clave generada por `face_key`);
la URL firmada devolvió 200 con el mismo contenido y el objeto desapareció tras
borrarlo. Suite completa: **118 passed** (113 previos + 5 de storage).

### Bloque 14 - OCR de horario desde foto o PDF escaneado (2026-10-22) - RF-07 - **✅ COMPLETADO Y VERIFICADO**

> Motivo: el Bloque 9 solo lee PDF con capa de texto y asigna UN docente y UN
> aula a todo el archivo. Un horario real de un ciclo llega como foto del
> cuadro impreso o PDF escaneado y tiene varios docentes y aulas. Este bloque
> cierra esa brecha sin tocar el modelo: **un archivo = un ciclo de un periodo**.

**Decisiones**

1. **Entrada:** PDF digital, PDF escaneado, JPG/PNG/WEBP (foto). Tope 10 MB y
   10 páginas. El archivo se procesa en memoria y se descarta (no va a R2).
2. **Dos vías de lectura:** primero `pdfplumber` (texto). Si hay pocas líneas
   útiles o el parser no encuentra bloques, se renderiza y se aplica OCR. Las
   imágenes van directo a OCR.
3. **RapidOCR** CPU (`rapidocr`, singleton perezoso, una sola inferencia a la
   vez con `asyncio.Semaphore(1)` + `asyncio.to_thread`). **pypdfium2** renderiza
   las páginas a 220 DPI (rueda pip, sin instalar poppler). Pillow aplica la
   orientación EXIF y reduce el lado máximo a 2500 px; RapidOCR recibe RGB. El
   enderezado y el umbral automáticos **no** se implementaron: la foto debe
   estar recta y el preview marca cualquier fila dudosa.
4. **Reconstrucción de líneas:** RapidOCR devuelve cajas + texto + confianza;
   se agrupan por `y` (tolerancia ~0.6×alto) y se ordenan por `x`. El parser
   reutiliza los regex del Bloque 9 (día, `HH:MM–HH:MM`, código, grupo).
5. **Periodo y ciclo explícitos:** el formulario pide `semester_label` (por
   defecto el vigente) y `cycle` (1–10). Los grupos nuevos se crean con ese
   periodo; los cursos nuevos con ese ciclo. Para varios ciclos se repite la
   importación (una por ciclo), sin adivinar el ciclo por página.
6. **Docente y aula por fila:** `teacher_id`/`room_id` del request siguen siendo
   los valores por defecto (compatibilidad) y cada bloque puede traer los suyos.
   Un grupo tiene UN docente: si dos filas del mismo grupo traen docentes
   distintos, el confirm responde 422. El aula sí puede variar por bloque.
7. **Confirmación todo o nada:** se reutiliza `add_block(commit=False)` con la
   validación RF-06/R9 (periodo del grupo, choques entre ciclos, franja RF-01).
   Un choque devuelve 409 con la fila culpable y no persiste nada.
8. **Idempotencia:** un bloque existente del mismo grupo con igual día y rango
   se omite y se cuenta en `omitidos`; no se duplica al reimportar.
9. **Cursos existentes:** se buscan por `code`; no se renombran ni se cambia su
   ciclo. Si no existen se crean con nombre editable de la vista previa. La
   vista previa marca `curso_nuevo: true`.
10. **Nunca escribir sin revisar:** el preview no toca la BD (solo auditoría de
    metadata) y la confirmación recibe las filas ya corregidas.

**Servicios**

- `services/ocr_extract.py` (nuevo): `leer_documento(filename, raw)` →
  `{tipo: pdf_texto|pdf_ocr|imagen, paginas, lineas: [{texto, x, y, confianza, pagina}]}`.
  Detecta el tipo por contenido real (cabecera `%PDF-`, magic de imagen), no
  por la extensión; aplica los límites y traduce errores a 415/422/413.
- `services/ocr_schedule.py`: acepta el documento extraído y devuelve
  `BloqueExtraido` con `pagina`, `linea`, `confianza` y `curso_nuevo`. Se
  conserva la firma actual para los tests del Bloque 9.
- `routers/courses.py`: `POST /courses/import-pdf` acepta PDF/JPG/PNG/WEBP y
  devuelve `tipo`, `paginas`, `confiables`, `ambiguos` y los bloques con
  `pagina`/`linea`. `POST /courses/import-pdf/confirm` añade
  `semester_label`, `teacher_id`/`room_id` por bloque y `omitidos`.
  Los paths actuales se mantienen (el frontend aún no los consume).

**Contrato (confirm)**

```json
{
  "semester_label": "2026-II",
  "cycle": 2,
  "teacher_id": 4,
  "room_id": 12,
  "bloques": [
    {"course_code": "ISA902", "course_name": "Álgebra", "group_code": "A",
     "weekday": 1, "start_time": "07:00", "end_time": "09:00",
     "teacher_id": 5, "room_id": 3}
  ]
}
```

Respuesta: `{cursos_creados, grupos_creados, bloques_creados, omitidos, total_bloques}`.

**Precisión y límites (honestos)**

- RapidOCR trae modelos ch/en por defecto; para nombres con tildes/ñ se evalúa
  el modelo **Latin** de PP-OCR y, si no mejora, se normaliza para comparar y
  se revisa a mano. Códigos, horas y DNI (dígitos) son los campos más fiables.
- Fotos: horario **impreso**, recto, con buena luz y sin sombras. La
  inclinación fuerte puede degradar el OCR. **Manuscrito no está soportado.**
- Toda fila con confianza baja, día/hora dudoso, curso sin grupo o aula sin
  detectar sale `confiable: false` + `nota`, y la UI la resalta.
- **Calibración pendiente** con 5 fotos y 5 PDF reales: se debe medir acierto
  en código/hora/día y documentarlo en el README. Las pruebas actuales usan
  imágenes sintéticas, un PDF escaneado generado y el servidor real; no
  sustituyen una muestra de horarios de la facultad.

**Tests**

- Parser puro con líneas inyectadas (sin OCR): día raro, rango invertido,
  columnas pegadas, dos cursos, grupo no detectado.
- OCR real con fixture generado (PIL/reportlab): PDF escaneado y foto con
  rotación 3° + ruido; se afirma sobre códigos/horas (tolerante), no sobre
  nombres completos.
- Preview: admin 200, docente 403, archivo vacío 422, >10 MB 413, >10 páginas 422.
- Confirm: periodo distinto al vigente, docente/aula por fila, choque 409 con
  rollback, reimportación idempotente (`omitidos`), curso existente no se
  renombra, grupo con dos docentes 422.
- `pytest -q` y una prueba manual con `curl -F` sobre uvicorn real.

**Dependencias:** `rapidocr==3.10.0`, `pypdfium2==5.13.0`. Los modelos OCR vienen
incluidos en `rapidocr` (probado sin descargas adicionales); para no pisar
`opencv-python` 4.10 se fija también `opencv-python-headless==4.10.0.84`.

**Estimación:** 1.5 días. **Entregable:** subir una foto del horario del ciclo
II de 2026-II → corregir docentes/aulas en la tabla → confirmar → ver la semana
en `/schedule?semester=2026-II&cycle=2`.

**Implementado (2026-10-22):** `services/ocr_extract.py` (PDF texto, PDF
renderizado con pypdfium2 y OCR con RapidOCR, reconstrucción de filas por
coordenadas), `ocr_schedule.py` (parser con página/confianza y fin de semana
marcado como ambiguo), `routers/courses.py` (acepta PDF/JPG/PNG/WEBP; preview
con `tipo` y reintento OCR si el PDF de texto no produce bloques; confirm con
`semester_label`, docente/aula por fila, `omitidos` e idempotencia).

### Bloque 15 - OCR de nómina de alumnos (2026-10-22) - RF-02/RF-03/RF-08 (ampliación) - **✅ COMPLETADO Y VERIFICADO**

> Motivo: el alta es de uno en uno y una nómina trae 30–40 alumnos. Se importa
> un **padrón impreso en tabla** (PDF o foto), se revisa y se confirman las
> cuentas. No se soportan fichas individuales ni manuscrito.

**Flujo**

1. `POST /students/import-preview` (multipart: `file`, `default_semester`) →
   no escribe nada. Detecta columnas por la fila de encabezado
   (CÓDIGO, DNI, APELLIDOS Y NOMBRES, CORREO, CICLO) y reconstruye filas por
   `y`; si el encabezado no aparece, usa regex por campo en cada línea.
2. La vista previa edita **todos** los campos y muestra por fila `confiable`,
   `errores[]` y la línea OCR original. Nada se guarda hasta confirmar.
3. `POST /students/import-confirm` recibe las filas corregidas, valida todo de
   nuevo en el servidor y crea las cuentas **fila por fila**: un duplicado no
   bloquea a los demás. Devuelve creados, omitidos, errores y (opcional)
   matriculados.

**Reglas**

- Campos: `code` (6 dígitos), `dni` (8), `full_name` (3–160), `email`,
  `semester` (1–12), `whatsapp` opcional. Se reutilizan `services/formats.py`
  y las validaciones de `accounts.create_account`.
- **Correo faltante** → `{code}@unamba.edu.pe` (o el dominio de
  `ALLOWED_EMAIL_DOMAIN`), marcado `email_generado: true` y editable. Si ya
  está tomado, la fila es error.
- **Duplicados:** mismo `code` en la BD → `omitido` (no se actualiza ni se
  pisa la contraseña); `dni`/`email` de otra cuenta → error de fila. Dentro del
  archivo, códigos repetidos → error en la segunda fila.
- **Cuentas:** clave temporal + `must_change_password` + correo RF-08. Si el
  correo falla, la cuenta queda creada y la fila lo reporta (comportamiento
  actual de `send_temporary_credentials`). Sin claves en logs ni respuestas.
- **Matrícula opcional:** si llega `group_id`, cada alumno creado o ya existente
  se matricula con R8 (cupo, un grupo activo por curso, cruces); los fallos se
  reportan por fila y no revierten la cuenta.
- **Privacidad:** el archivo se descarta, no va a R2 ni a logs; la auditoría
  guarda solo conteos y nombre de archivo.
- Tope: 10 MB, 10 páginas, 200 filas. Solo admin.

**Contrato (preview)**

```json
{
  "tipo": "pdf_ocr",
  "paginas": 2,
  "total": 38,
  "listos": 35,
  "con_error": 3,
  "alumnos": [
    {"fila": 1, "code": "221181", "dni": "74581236",
     "full_name": "QUISPE MAMANI, RAUL", "email": "221181@unamba.edu.pe",
     "email_generado": true, "semester": 2, "confiable": true,
     "errores": [], "nota": null, "linea": "221181 74581236 ...", "pagina": 1}
  ]
}
```

**Contrato (confirm)** `{alumnos: [...], group_id?: number}` →
`{creados, omitidos, matriculados, errores: [{fila, code, motivo}], total}`.

**Servicios**

- `services/ocr_roster.py`: columnas por `x` del encabezado + regex de respaldo;
  limpieza de nombres (espacios, puntos, guiones) sin inventar apellidos;
  detección de `CICLO` y de correo.
- `services/students_import.py`: valida y crea por fila reutilizando `accounts`
  (se extraen los helpers de validación para no duplicar reglas); matrícula vía
  `services/enrollments`. `create_account` sigue igual para el alta individual.
- `routers/catalog.py`: los dos endpoints, `RequireRole(ADMIN)` y auditoría
  `importacion_alumnos_preview` / `importacion_alumnos_confirmada`.

**Tests:** parser con cajas OCR simuladas (encabezado, columna partida, correo
ausente, código repetido), validación de filas, confirm con 38 filas y 1
duplicada (37 creadas + 1 omitida), matrícula opcional con grupo lleno, `403`
a docente, `422` archivo sin tabla, `413` >10 MB, y que la auditoría no guarde
datos personales.

**Estimación:** 1.5 días. **Entregable:** subir la foto de una nómina →
corregir 3 filas → confirmar → 37 alumnos en `/students`, 1 reportado como
duplicado y, si se eligió grupo, matriculados.

**Implementado (2026-10-22):** `services/ocr_roster.py` (columnas por
encabezado + regex de respaldo, correo generado, duplicados en archivo),
`services/students_import.py` (duplicados en BD, preview de solo lectura y
confirmación por fila con `create_account`; auditoría sin PII) y los endpoints
`POST /students/import-preview` + `POST /students/import-confirm`.

**Verificación (2026-10-22):** `tests/test_ocr_images.py` (7) y
`tests/test_students_import.py` (6) cubren OCR real de imágenes y PDF escaneado,
periodo/ciclo, aula por fila, idempotencia, dos docentes en un grupo, nómina con
correo generado, duplicados y matrícula opcional. Suite completa sin
`test_vision.py`: **122 passed**. Además, contra el `fastapi dev` real por HTTP
multipart: la nómina devolvió una fila con correo generado y el horario un
bloque, ambos con 200.

### Bloque 16 - Notificaciones por rol en el sistema y por correo (2026-10-23) - RF-24 - **✅ COMPLETADO Y VERIFICADO**

> Las alertas DPI ya salían por correo. Faltaba una bandeja real para admin,
> docente y estudiante, con lógica por evento y sin duplicar correos ni avisos.

**Modelo y endpoints**

- `notification` (`db/012_notifications.sql`; también consolidada en
  `001_schema.sql`): `user_id`, `kind`, `title`, `message`, `link`, `severity`,
  `read_at`, `dedupe_key`, estado de correo e intentos. FK con `ON DELETE CASCADE`.
- `services/notification_center.py`: alta de avisos por usuario o por rol,
  deduplicación por usuario y helpers por evento. `despachar_correos_pendientes`
  envía en lote con `send_notification_email`, reintenta hasta 3 veces y separa
  el envío del request.
- `GET /notifications/unread-count` (para el polling de 10 s del cliente),
  `GET /notifications?limit=&before_id=&unread_only=` (se pide al abrir la
  bandeja, sin polling), `POST /notifications/{id}/read` y
  `POST /notifications/read-all`. Cada endpoint filtra por el usuario autenticado.
- APScheduler tiene un job independiente `despacho_correos` para no bloquear el
  cierre de sesiones; `FRONTEND_BASE_URL` arma el CTA absoluto de los correos.

**Matriz de eventos**

| Rol | Eventos |
|---|---|
| Estudiante | Alerta/límite DPI, justificación registrada o eliminada, clase cancelada, rectificación de asistencia |
| Docente | Sesión cerrada sin marcas, clase cancelada, justificación de su curso, alumno que supera el límite DPI |
| Admin | Sesión cerrada sin marcas, justificación registrada por docente, dispositivo sin conexión, alumno que supera el límite DPI |

**Correo:** DPI (flujo existente), cancelación de clase, sesión por revisar y
rectificación. La supervisión al admin y los avisos de justificación quedan solo
en la bandeja para no generar ruido.

**Verificación (2026-10-23):** `tests/test_notifications.py` (6) cubre aislamiento
por usuario, contador/listado, lectura individual y masiva, justificaciones,
cancelación, revisión, rectificación y cola de correo. Suite completa sin
`test_vision.py`: **178 passed**. En el navegador real: badge, polling de 10 s,
lista bajo demanda, marcar leída, marcar todas, estado vacío y navegación al
evento.

### Bloque 10 - Calidad y demo final (1–2 días) - **se ejecuta DESPUÉS de los Bloques 11, 13, 14 y 15**
- [x] Suite pytest completa (motor, auth, catálogo, OCR, portal, matriz de roles…) contra la base `fareas`.
- [x] Producción simple: `fastapi run` + Cloudflare Tunnel; el build de Angular se sirve desde el propio FastAPI (`app/frontend.py`, activado con `FRONTEND_DIST_DIR`; un solo origen, sin CORS) ✅. Las variables de producción están en `PLAN-FRONTEND.md` F7 (7.6).
- [x] README: protocolo ESP32, scripts de simulación y puesta en marcha; el guion de demo está en `PLAN-FRONTEND.md` F7 (7.9).
- **Entregable:** demo end-to-end: PDF/foto → horario y nómina → matrícula → enrolamiento → video/entrada real → asistencia → reportes.

---

## 4. Dispositivos reales (cámara, ESP32, LED y buzzer)

El armado, la instalación de programas en Windows, la configuración del `.env`, el firmware (`firmware/fareas_nodo/fareas_nodo.ino`) y la lista de verificación están en `PLAN-FRONTEND.md` → **F7**. Los scripts `test_rtsp.py`, `simulate_camera.py` y `simulate_esp32.py` siguen en `scripts/`.

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
3. **Para activar R2 (Bloque 13):** crear un API token con permiso `Object Read & Write` limitado al bucket `fareas-assets` y pasarme `Access Key ID` + `Secret Access Key`. No hace falta dominio público. CORS solo si el navegador sube directo o descarga con `fetch`/blob; con `<img>`/`<a>` directo sobre la URL firmada no se necesita.

---

## 8. Cronograma restante

| Semana | Bloques | Hito |
|---|---|---|
| 1 | ~~1, 3~~ ✅ | ~~App bajo app/main.py + login JWT~~ - COMPLETADO |
| 2 | ~~4, 5~~ ✅ | ~~Malla académica + reconocimiento funcionando con video/MP4~~ - COMPLETADO |
| 3 | ~~6, 7~~ ✅ | ~~Motor de asistencia + protocolo ESP32~~ — COMPLETADO (el ESP32 físico se conecta cuando lo armes) |
| 4 | ~~8, 9~~ ✅ | ~~Dashboard + reportes + OCR~~ — COMPLETADO |
| 5 | **11 (reglas de negocio)** ✅ | Semestre, cupos, transferencias, justificaciones, DPI con aviso único, seguridad y reportes por grupo — COMPLETADO (ver §3, Bloque 11) |
| 6 | **13** ✅ | R2 (fotos/adjuntos) — COMPLETADO: fotos de enrolamiento, adjunto de justificación (UI en F4.1) y foto de perfil (Bloque 16) |
| 7 | **14 + 15** ✅ | OCR de horario (foto/PDF escaneado) + importación de nómina de alumnos — COMPLETADO |
| 8 | **10** | Calidad y demo final (README, demo E2E, tunnel) |

---

## 9. Autorización por rol

La matriz por pantalla está en `PLAN-FRONTEND.md` §7. Pendientes del lado backend:

- [x] Limpieza periódica (cada 6 h) de `refresh_token` vencidos (7 días de gracia) o revocados hace más de 30 días y de `password_otp` vencidos hace más de un día: `services/maintenance.py`. La bitácora `audit_log` no se borra automáticamente (evidencia de auditoría).
- [x] Test parametrizado de permisos: `tests/test_role_matrix.py` recorre 25 endpoints de lectura con admin, docente y estudiante (y sin token). Corrigió un fallo real: `/dashboard/summary` y `/stats/*` aceptaban a estudiantes.

---

## 10. Bloque 16 - Portal del estudiante, foto de perfil y servicio del frontend (2026-10-23) - ✅ COMPLETADO Y VERIFICADO

- **Portal del estudiante** (`routers/me.py`, solo rol estudiante): `GET /me/schedule`, `/me/courses` y `/me/justifications`; `tests/test_student_portal.py` (7). Detalle de pantallas en `PLAN-FRONTEND.md` §8.
- **Foto de perfil** (cualquier rol): `PUT /auth/me/avatar` (multipart) y `DELETE /auth/me/avatar`; `UserOut.avatar_url` en `/auth/login` y `/auth/me`. `services/avatars.py` valida que sea una imagen real (JPG/PNG/WEBP, hasta `AVATAR_MAX_UPLOAD_MB` = 5 y 25 Mpx), corrige la orientación, la recorta en cuadrado de 256 px y la guarda como JPEG sin metadatos EXIF en `avatars/{user_id}/{uuid}.jpg`. La URL firmada dura `AVATAR_URL_EXPIRE_SECONDS` (12 h). Auditoría `avatar_actualizado` / `avatar_eliminado`. BD: `db/011_avatar.sql` (`app_user.avatar_key`, ya consolidado en `001`). `tests/test_avatar.py` (7).
- **Decisión de privacidad:** la foto de perfil es independiente del enrolamiento facial. La foto biométrica nunca se reutiliza como avatar: el consentimiento (Ley 29733) cubre solo el reconocimiento, el bucket es privado y solo la ve el administrador en `/faces`.
- **Frontend servido por FastAPI** (`app/frontend.py`, `FRONTEND_DIST_DIR`): estáticos más fallback a `index.html`; `/api/v1`, `/docs` y `/openapi.json` quedan intactos. `tests/test_frontend_mount.py` (5).
- **Pendiente:** mostrar la foto de los demás usuarios en listados (alumnos, matrículas, dashboard) exige que esos endpoints devuelvan `avatar_url`; hoy ahí se muestran iniciales.

### Cambios de la revisión final (2026-10-23)
- **Estado de las cámaras (RF-35):** `camera_loop` marca `device.is_online` y `last_heartbeat` al abrir el stream, lo refresca cada 30 s y lo apaga si la fuente se cae; al arrancar deja todas en fuera de línea. `GET /dashboard/summary` cuenta ahora cámaras realmente en línea (`tests/test_camera_status.py`).
- **Alcance del docente en riesgo:** `GET /dpi/at-risk` y las alertas del dashboard usan los alumnos matriculados en **sus grupos** del periodo, no todos los del curso (`tests/test_dpi_teacher_scope.py`).
- **Enrolamiento facial:** solo se guarda en R2 la primera foto como portada (las demás se descartan tras generar el embedding). Al reenrolar se borran el registro y la foto anteriores; antes quedaban acumuladas (`tests/test_enroll_replace.py`). La validación de consistencia compara cada foto con el promedio de las demás (≥ 0.40).

---

## 11. Bloque 17 - Importación de la malla curricular (2026-10-24) - ✅ COMPLETADO Y VERIFICADO

> Motivo: registrar de una vez todos los cursos (código, nombre y ciclo) de una malla impresa en la que cada ciclo es una
> columna, en vez de dar de alta un curso por vez. Reutiliza el motor de lectura del Bloque 14 (`ocr_extract`).

- **Endpoints (solo admin, `routers/curriculum.py`):**
  - `POST /courses/import-curriculum` (multipart: `file` y `default_cycle` opcional) → previsualización **sin escribir nada**: por curso `code`, `name`, `cycle`, `confiable`, `nota`, `linea`, `pagina`, `ya_existe` y el curso existente. Resumen: `total`, `listos`, `por_revisar`, `ya_existentes` y `ciclos`.
  - `POST /courses/import-curriculum/confirm` → recibe `{cursos: [{code, name, cycle}]}` (máx. 200), rechaza códigos repetidos (422), **omite los que ya existen sin modificarlos** y crea el resto en una sola transacción. Auditoría `importacion_malla_preview` / `importacion_malla_confirmada`.
- **Parser (`services/ocr_curriculum.py`):**
  1. Detecta los títulos de ciclo («PRIMER CICLO», «SÉPTIMO CICLO», «CICLO IV», «III CICLO», «2° CICLO», «CICLO 9»), incluso partidos en varias palabras (PDF con texto).
  2. **Columnas:** si los títulos están en una misma franja, cada código (`AIS11`, `AGG20`: 2-5 letras y 1-3 dígitos) se asigna a la columna más cercana, y su nombre son las líneas de texto de esa columna entre el código anterior y el suyo (máx. ~6 alturas de código hacia arriba). Las flechas y los símbolos sueltos (confianza < 0.5, sin letras, de un solo carácter salvo «a/e/o/u/y» y números romanos) se descartan.
  3. **Secciones:** si los títulos están en vertical, cada fila con un código toma el resto de la fila como nombre y las filas de continuación se anexan.
  4. Sin títulos: varias columnas de códigos → ciclos por posición (I, II, III…) marcados «por verificar»; una sola columna → usa `default_cycle`, y si no hay, deja el ciclo vacío para que el usuario lo indique.
  5. Marca como no confiable: nombre vacío o muy corto, lectura con confianza < 0.85, ciclo estimado y códigos repetidos en el archivo.
- **Verificación:** `tests/test_ocr_curriculum.py` (23): casos sintéticos (columnas, nombres de varias líneas, ruido, duplicados, sin títulos, lista vertical), PDF con texto, **la imagen real de la malla** (`tests/fixtures/malla_ais.png`: 63 cursos, `7-6-6-6-6-6-7-7-6-6` por ciclo) y los endpoints (preview, confirm, permisos, 415/422). Contra el servidor real: 63 cursos, 62 listos, 1 por revisar.
- **Límites:** la imagen debe verse nítida y recta; un diagrama muy borroso o con códigos tapados por flechas saldrá «por revisar». No se actualizan cursos existentes (para cambiar un nombre o ciclo se edita el curso).

---

## 12. Bloque 18 - Matrícula masiva y autogestión (2026-10-24) - ✅ COMPLETADO Y VERIFICADO

> Reutiliza `services/enrollments.py` (reglas R8: cupo, un grupo activo por curso, sin cruce de horario, retiro y transferencia) y
> añade la matrícula de varios alumnos a la vez, el paquete «ciclo + letra de grupo» y la matrícula por el propio estudiante.

- **BD:** `db/012_ventana_matricula.sql` (`app_settings.enrollment_start` y `enrollment_end`, DATE; ya consolidado en `001`). La ventana está abierta si hoy (hora de Perú) está entre ambas fechas, **inclusive**; sin fechas, cerrada. `PATCH /settings` las acepta y rechaza inicio > fin.
- **Administrador (`routers/enrollment_center.py`):**
  - `GET /enrollment/package-letters?cycle=` — letras de grupo del ciclo con cuántos cursos cubre cada una.
  - `GET /enrollment/package?cycle=&group_code=` — grupos del paquete con docente, horario, cupo y libres, y los cursos del ciclo que **no tienen** esa letra en el periodo vigente.
  - `POST /enrollment/resolve-students` — resuelve códigos de matrícula (informa los no encontrados).
  - `POST /enrollment/bulk` (`student_ids`/`student_codes` + `group_ids`) y `POST /enrollment/package` (`student_ids`/`student_codes` + `cycle` + `group_code`): hasta 300 alumnos y 20 grupos; cada par alumno-grupo se procesa por separado y devuelve `ok`, `skipped` (ya estaba) o `failed` con el motivo; un fallo no revierte los demás. Auditoría `matricula_masiva` / `matricula_por_ciclo` más la de cada matrícula.
- **Estudiante (`routers/self_enrollment.py`, solo rol estudiante):** `GET /me/enrollment` (periodo, ciclo del alumno y ventana), `GET /me/enrollment/offer?cycle=` (todos los grupos activos del periodo con cupo, horario, `mine`, `current_group_code` si ya cursa otro grupo del mismo curso y `conflict` con el curso con el que se cruza), `POST /me/enrollment`, `DELETE /me/enrollment/{group_id}`, `POST /me/enrollment/{group_id}/transfer` y `POST /me/enrollment/package`. Todo lo que escribe exige la ventana abierta (403 con el mensaje) y solo actúa sobre el propio estudiante; el administrador sigue pudiendo matricular fuera de la ventana. Las matrículas hechas por el estudiante quedan auditadas con él como actor.
- **Tests:** `tests/test_enrollment_center.py` (9: vista previa del paquete, parejas ok/fallidas/omitidas, grupo lleno, cruce de horario, códigos desconocidos, permisos, ventana cerrada por defecto, alta/cambio/retiro del estudiante, paquete del estudiante, ventana invertida) y la matriz de roles ampliada. Los alumnos de una tanda se procesan ordenados por código para que el reparto de los últimos cupos sea predecible.
- **Nota de pruebas:** `test_no_abre_sesion_sin_docente_o_aula` dependía de que no hubiera ningún otro bloque real el lunes a las 08:05 (la base compartida tiene un horario real en esa hora); ahora comprueba solo la sesión de su propio escenario.
- **Fuera de alcance (anotado):** aprobación de solicitudes, límite de créditos o de cursos por estudiante, prerrequisitos de la malla, lista de espera para cursos llenos y notificación por correo al matricular.

---

## 13. Bloque 19 - Cursos sin grupo y grupo inicial implícito (2026-10-24) - ✅ COMPLETADO Y VERIFICADO

> Sin cambios de esquema: un grupo ya podía existir sin docente; lo que cambia es **quién lo crea y cuándo**.

- **Grupo inicial implícito (`services/course_groups.py`):** `POST /courses/{course_id}/blocks` añade un bloque a un **curso**. Si el curso no tiene grupos activos en el periodo vigente se crea el grupo `A` (cupo 40, sin docente) en la misma transacción; si tiene uno se usa; si tiene varios exige `group_id` (422 «tiene varios grupos») y un `group_id` ajeno al curso devuelve 404. Si el bloque falla (choque de aula o docente), el grupo recién creado se revierte. La respuesta indica `group_code` y `group_created`. Auditoría `grupo_creado` con `implicito: true`.
- **Docente opcional:** `POST /courses/{id}/groups` ya no exige `teacher_id`. Nuevo `PATCH /groups/{id}` (`teacher_id`, `null` lo quita; `capacity`, que no puede ser menor a los matriculados); valida docente activo y que no choque con el horario del grupo (409). Auditoría `grupo_actualizado`.
- **Asistencia sin docente:** `bloques_candidatos` y `abrir_sesiones_del_dia` ya no exigen docente; siguen exigiendo **aula** y horario. Un docente solo ve los grupos que tiene asignados, así que lo registrado antes de asignarlo lo ve el administrador y, al asignarlo, el docente.
- **Aviso de curso lleno:** `GET /courses/overflow` (admin) lista los cursos cuyos grupos activos del periodo están **todos** llenos; `GET /dashboard/summary` añade `cursos_llenos` (0 para docentes). Mientras tanto la matrícula sigue rechazando con «Grupo lleno»: el administrador decide cuándo crear el grupo B.
- **Matrícula por ciclo:** `POST /enrollment/package` con la letra `A` crea el grupo inicial de los cursos del ciclo que no tienen ninguno y lo informa en `created_groups`; con otras letras no crea nada. La vista previa marca `will_create_group` en esos cursos.
- **Tests:** `tests/test_implicit_groups.py` (10) — grupo inicial, docente opcional, reversión de un bloque fallido, varios grupos, asignar/quitar docente, choque de docente, cupo, aviso de curso lleno (y su desaparición con un grupo nuevo), paquete por ciclo y permisos; `test_sessions_lifecycle` ahora comprueba que **sin aula** no se abre sesión y que **sin docente sí**.
- **Fuera de alcance (anotado):** crear automáticamente el grupo B al llenarse (se decidió que lo haga el administrador), lista de espera y copiar el horario de un grupo a otro.

### Ajustes de la autogestión (2026-10-24, segunda pasada) - Bloque 18
- **Oferta por curso:** `GET /me/enrollment/offer` ahora incluye también los cursos **sin grupo ni horario** (`group_id: null`, `will_create_group: true`, grupo «A», 40 cupos), para que el estudiante pueda marcarlos.
- **Matrícula por selección:** `POST /me/enrollment/bulk` (`items: [{course_id, group_id?}]`, máx. 30) reemplaza a `POST /me/enrollment/package`. Por curso: con un solo grupo lo usa; sin grupos **crea el grupo A sin docente**; con varios exige `group_id`. Cada curso se procesa por separado (`ok`, `skipped` o `failed` con motivo) y los válidos se guardan aunque otros fallen. Exige la ventana abierta.
- **Retirados:** `POST /me/enrollment/package` y `GET /me/courses` (no tenían uso tras quitar «Mis cursos» y el ciclo completo).
- **Admin:** `GET /enrollment/package-letters` incluye la letra `A` cuando hay cursos del ciclo sin grupo, para poder matricular un ciclo recién cargado.
- **Tests:** `tests/test_enrollment_center.py` cubre la selección (válidos, lleno, cruce, curso sin grupo, varios grupos, repetido, ventana cerrada) y la oferta con cursos pendientes.

