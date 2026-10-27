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
- **Cloudflare R2** (bucket privado `fareas-assets`, URLs firmadas) para fotos de enrolamiento y adjuntos (Bloque 13)
- **OCR local**: RapidOCR (ONNX) + pypdfium2 para PDF escaneado y fotos; no se envían documentos a servicios externos

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
│   ├── tables.py             # 16 entidades SQLModel que MAPEAN db/001_schema.sql
│   ├── schemas/              # DTOs: auth.py, common.py (Page/Message), …
│   ├── ai/                   # pipeline de visión (Bloque 5): detector, embedder,
│   │                         #   recognizer, pipeline (Tabla 8), frame_source, runtime
│   ├── services/             # lógica de negocio (routers delgados)
│   │   ├── accounts.py       # alta docente/estudiante + clave temporal (RF-02/03/08)
│   │   ├── audit.py          # bitácora RF-32 dentro de la transacción
│   │   ├── emailer.py        # credenciales (RF-08), OTP de recuperación/cambio (RF-12) y aviso de clave actualizada
│   │   ├── notifications.py  # alertas DPI al cierre de sesión (RF-24)
│   │   ├── refresh_tokens.py # refresh opaco, rotación y revocación por familia
│   │   ├── errors.py         # DomainError/ConflictError/NotFoundError → handlers HTTP
│   │   ├── attendance_engine.py  # resolver sesión, marca única, cierre RF-26, DPI RF-24
│   │   ├── session_scheduler.py  # APScheduler: cierre automático cada 60 s (RF-26)
│   │   ├── camera_loop.py    # cámaras RTSP → pipeline → marcas → ESP32 (2 fps)
│   │   ├── schedule.py       # validación de choques de horario (RF-06)
│   │   ├── ocr_extract.py    # PDF texto/escaneado o foto → líneas con coordenadas
│   │   ├── ocr_schedule.py   # líneas del horario → bloques (RF-07, Bloques 9/14)
│   │   ├── ocr_roster.py     # nómina impresa → alumnos (Bloque 15)
│   │   ├── students_import.py # preview y alta masiva de alumnos (Bloque 15)
│   │   ├── exports.py        # reportes Excel/PDF con encabezado institucional (RF-16)
│   │   └── storage.py        # Cloudflare R2 (fotos) + URLs firmadas (Bloque 13)
│   └── routers/
│       ├── auth.py           # login JWT + refresh, /me, cambio de clave con OTP (RF-11/RF-12)
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
├── storage/                  # fallback local de desarrollo/pruebas; el destino normal es R2 (Bloque 13)
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

fastapi dev          # entrypoint de pyproject.toml (app.main:app) or preview led  fastapi dev --host 0.0.0.0  conection esp32

# alternativas: uvicorn app.main:app --reload  |  python main.py
```

- Swagger: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/v1/health> →
  `{"status":"ok","database":"ok","users":9}` con el seed cargado
- **R2:** el bucket `fareas-assets` y el endpoint ya están en `.env`/`.env.example`.
  Completa `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` con un token limitado al
  bucket (`Object Read & Write`). Con `R2_ENABLED=true` y claves, las fotos de
  enrolamiento van a R2 con URL firmada; sin claves, el sistema cae al
  `storage/` local (útil para tests y desarrollo offline).

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
3. **Para las BD que ya existen va ADEMÁS un ALTER numerado nuevo**
   (`db/003_algo.sql`, `004_…`): el paso a paso, en orden, para la BD que ya
   tiene datos. Debe ser **re-ejecutable** (`ADD COLUMN IF NOT EXISTS`,
   `CREATE INDEX IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS`, bloques `DO $$
   … EXCEPTION WHEN duplicate_object THEN NULL; END $$`) y nunca recrea ni
   borra datos.
4. **Cuando TODO el equipo ya aplicó el ALTER, SE BORRA** (su contenido ya vive
   en `001` + `002`) y se deja constancia en el commit. Así quedan siempre 2
   scripts: un dev nuevo instala con `001` + `002`, y una BD vieja se pone al
   día con el ALTER pendiente.
5. **Al borrar un ALTER, anótalo aquí** (y siembra la fecha):

   | Archivo borrado | Fecha | Qué consolidó |
   |---|---|---|
   | `005_reglas_negocio.sql`, `006_session_cancelada.sql`, `007_vistas_reglas.sql` | 2026-10-16 | Reglas R1–R13: columnas nuevas, enum `cancelada` y las vistas R5/R6/R7 |
   | `003_aula_por_bloque.sql`, `004_aula_solo_en_bloque.sql` | 2026-10-22 | Aula por bloque y eliminación de `course_group.room_id`; consolidadas en `001`/`002` |

6. El `ADD VALUE` de un enum no se puede usar en la misma transacción que lo
   agrega: va en su propio archivo (por eso `006` existió como archivo aparte).
7. **`001` reproduce el DDL tal cual está en la BD, orden de columnas incluido.**
   Si un ALTER agrega una columna, esa columna se escribe **al final** de su
   tabla en `001` (es donde queda físicamente y `pg_dump` respeta el orden).
   Así el `diff` de abajo sigue siendo una comprobación real.
   **Excepción: DROP COLUMN.** PostgreSQL no cierra el hueco que deja una
   columna borrada, así que en la BD migrada las columnas posteriores quedan
   con un `attnum` corrido y un `pg_dump` las lista en el mismo orden lógico
   pero no idéntico al de una instalación nueva. En ese caso el diff se revisa
   por nombre + tipo + nulabilidad + default (la estructura es la misma; solo
   cambia la numeración interna), y se anota en el ALTER.

Un ALTER **pendiente** (aún no aplicado por todo el equipo) se corre una vez:

```bash
psql -U postgres -d fareas -v ON_ERROR_STOP=1 -f db/003_ciclo_curso.sql
```

**Pendiente ahora mismo:** `db/003_ciclo_curso.sql` (agrega `course.cycle`
1–10, rellena los cursos existentes con el ciclo 9 y crea el CHECK),
`db/004_docente_aula_opcionales.sql` (docente del grupo y aula del bloque
nullable, más `v_today_attendance` con `LEFT JOIN room`) y
`db/005_refresh_tokens.sql` (tabla `refresh_token` para las sesiones con
refresh), `db/008_password_otp.sql` (tabla `password_otp` para los códigos de
verificación), `db/009_justificacion_documento.sql` (columna
`justification.document_key`), `db/010_defaults_app_settings.sql` (DEFAULT de
`app_settings`: umbral facial 0.55 y DPI 20/30) y `db/012_notifications.sql`
(tabla `notification` para la bandeja y la cola de correo). Quien ya los aplicó: borra su línea cuando todo
el equipo los tenga, junto con el archivo.

Lo que se revisa al actualizar: que una BD **vieja + ALTER** y una instalación
**nueva con `001` + `002`** queden idénticas. Ese es el contrato de la regla.

```bash
# 1) BD "vieja": los scripts de git ANTES del cambio, y encima el ALTER nuevo
git show HEAD:back-fareas/db/001_schema.sql > /tmp/old_001.sql
git show HEAD:back-fareas/db/002_seed.sql > /tmp/old_002.sql
createdb -U postgres fareas_mig
psql -U postgres -d fareas_mig -v ON_ERROR_STOP=1 -f /tmp/old_001.sql
psql -U postgres -d fareas_mig -v ON_ERROR_STOP=1 -f /tmp/old_002.sql
psql -U postgres -d fareas_mig -v ON_ERROR_STOP=1 -f db/003_ciclo_curso.sql
psql -U postgres -d fareas_mig -v ON_ERROR_STOP=1 -f db/003_ciclo_curso.sql  # 2ª vez: re-ejecutable

# 2) instalación nueva: los 2 scripts ya actualizados
createdb -U postgres fareas_nueva
psql -U postgres -d fareas_nueva -v ON_ERROR_STOP=1 -f db/001_schema.sql
psql -U postgres -d fareas_nueva -v ON_ERROR_STOP=1 -f db/002_seed.sql

# 3) los dos DDL deben ser IGUALES
pg_dump -U postgres -d fareas_mig   --schema-only --no-owner --no-acl > /tmp/mig.sql
pg_dump -U postgres -d fareas_nueva --schema-only --no-owner --no-acl > /tmp/nueva.sql
diff <(grep -v '\restrict' /tmp/mig.sql) <(grep -v '\restrict' /tmp/nueva.sql)   # vacío

# 4) y la suite contra la BD migrada
DATABASE_URL=... pytest -q
```

> `pg_dump` 17 mete un token aleatorio `\restrict`/`\unrestrict` en cada dump:
> por eso el `grep -v` - es lo único que puede aparecer en el `diff`.

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

Endpoints de auth: `POST /auth/login` · `POST /auth/refresh` · `POST /auth/logout`
· `POST /auth/logout-all` · `GET /auth/me` · `POST /auth/change-password`
· `POST /auth/recover` → `/verify` → `/reset` (OTP 6 dígitos, RF-12).

**Cambio de contraseña con OTP (2026-10-22, RF-11/RF-12):**

1. `POST /auth/change-password/otp` `{current_password}` - valida la clave actual
   y envía un código de 6 dígitos al correo institucional. Responde el correo
   **enmascarado**, `expires_in` (600 s) y `resend_in` (60 s). Cooldown de 60 s.
2. `POST /auth/change-password/otp/verify` `{code}` - valida el código; el OTP
   queda marcado como verificado (`verified`).
3. `POST /auth/change-password` `{current_password, new_password}` - exige y
   **consume** el OTP verificado, actualiza la clave y devuelve `access_token`.

Reglas del flujo:

- El OTP es un **segundo factor**: no reemplaza la contraseña actual.
- TTL 10 min, máximo 5 intentos, un solo uso y binding por `(user_id, purpose)`:
  un código de recuperación no sirve para el cambio voluntario (ni al revés).
- Los códigos viven en la tabla `password_otp` (hash Argon2, una fila por
  `user_id` + `purpose`), no en memoria: sobreviven a un reinicio del backend
  (incluida la recarga de `fastapi dev`) y funcionan con varios workers. La fila
  queda con `consumed_at` al usarse, así que un segundo intento responde
  "Este código ya se usó" en lugar de un error genérico.
- Pedir otro código dentro de los 60 s de cooldown no envía correo; el frontend
  bloquea el reenvío y muestra los segundos restantes.
- La clave temporal (`must_change_password=true`) se cambia **sin OTP** en el
  primer login: el usuario acaba de recibirla y el guard lo obliga a cambiarla.
- Al cambiar/restablecer se incrementa `app_user.token_version` (`ver` en el JWT):
  los tokens viejos quedan inválidos y la respuesta entrega uno nuevo para no
  cerrar la sesión actual. El frontend lo persiste en `AuthService.changePassword`.
- Se audita `password_change_otp`, `password_changed` y `password_reset`
  (RF-32) y se envía un aviso de seguridad por correo.

### Refresh tokens (2026-10-22)

- `POST /auth/login` devuelve `access_token`, `refresh_token`, `token_type`,
  `expires_in` (acceso) y `refresh_expires_in` (refresh).
- `POST /auth/refresh {refresh_token}` rota el token y devuelve un par nuevo.
  El refresh token es opaco y de alta entropía; en BD solo se guarda su hash
  SHA-256, nunca el valor original.
- Cada login crea una **familia** de refresh tokens. Si se reutiliza un token ya
  rotado, se revoca toda la familia y se audita como `refresh_token_reuse`.
- `POST /auth/logout {refresh_token}` revoca la familia de forma idempotente
  (204). `POST /auth/logout-all` revoca todas las sesiones e invalida también
  los access tokens incrementando `app_user.token_version`.
- La sesión tiene vencimiento absoluto: `REFRESH_TOKEN_EXPIRE_DAYS` (30 días).
  Rotar no extiende ese plazo. El access token sigue durando
  `ACCESS_TOKEN_EXPIRE_MINUTES` (120 min).
- Cambio/restablecimiento de clave, reenvío de clave temporal y desactivación de
  cuenta revocan los refresh tokens. El cambio de clave devuelve un par nuevo
  para no cerrar la sesión actual.
- BD existente: aplicar `db/005_refresh_tokens.sql`. Una instalación nueva ya
  incluye la tabla en `db/001_schema.sql`.
- **Fase frontend pendiente:** persistir el refresh token de forma segura e
  implementar un refresh *single-flight* ante 401. Por ahora el backend lo
  entrega en JSON; para producción web conviene moverlo a cookie HttpOnly.

### Endpoints del Bloque 4 - catálogo académico (RF-02…RF-10, RF-22, RF-32, RF-34, RF-35)

- **Aulas:** `GET/POST /rooms` · `PATCH /rooms/{id}` - paginado con `?page=&page_size=&q=`
- **Dispositivos:** `GET/POST /devices` · `PATCH /devices/{id}` · `GET /devices/status` (público, RF-35)
- **Docentes:** `GET/POST /teachers` (alta envía clave temporal por correo, RF-08)
- **Estudiantes:** `GET/POST /students` (`?semester=` para filtrar por ciclo)
- **Cuentas:** `GET/PATCH /accounts/{id}` · `POST /accounts/{id}/send-temp-password` (reenvía credenciales RF-08)
- **Cursos/grupos/bloques:** `GET/POST /courses` · `PATCH/DELETE /courses/{id}` (con `cycle` 1–10; un curso con grupos no se elimina) · `GET /courses/{id}/groups` · `POST /courses/{id}/groups`
  · `GET/POST /groups/{id}/blocks` · `PATCH/DELETE /blocks/{id}` · `DELETE /groups/{id}`
  · `POST /groups/{id}/activate` (deshace la baja lógica) · `GET /schedule?semester=&cycle=&course_id=&teacher_id=&room_id=`
  (semana completa del periodo, una sola consulta) · `GET /groups?semester=&cycle=`
  -
  **choques RF-06:** misma aula (la **del bloque**, R9) o mismo docente en rangos que se cruzan → 409;
  se validan entre **todos los ciclos del mismo periodo**. Semana lectiva **Lun–Vie** (`weekday` 1..5). El aula va SOLO en el bloque
  (`room_id` obligatorio): el grupo no guarda aula y su ausencia responde 422.
  El **ciclo** (`course.cycle`, 1–10) es la malla del curso: el grupo lo hereda y el periodo sigue siendo
  `course_group.semester_label` (2026-II).
- **Matrículas RF-22:** `GET/POST /groups/{id}/students` · `DELETE /groups/{id}/students/{student_id}`
- **Calendario:** `GET/POST /holidays` · `DELETE /holidays/{id}` · `GET/POST /justifications`
  · `DELETE /justifications/{id}` · `POST/DELETE /justifications/{id}/document` ·
  `GET/PATCH /settings` (RF-34)
- **Bitácora RF-32:** `GET /audit-log` (solo admin; filtros `action`, `entity`, `entity_id`, `actor_id`, `since`)

Toda escritura queda registrada en `audit_log` con actor, IP y valores antes/después (JSONB).

### Bloque 13 - adjuntos de justificación (R2)

- `POST /justifications/{id}/document` (multipart `file`): admin o el docente que
  creó la justificación. Acepta **PDF, JPG o PNG de hasta 10 MB**, validando la
  firma real del archivo (no la extensión). Lo sube a
  `justifications/{id}/{uuid}.{pdf|jpg|png}` en R2 (fallback `storage/` local).
- `GET /justifications` devuelve `document_url` con una **URL firmada de 900 s**
  cuando el adjunto está en R2; el enlace externo viejo (`document_url` de la
  creación) se conserva como compatibilidad.
- `DELETE /justifications/{id}/document` borra el objeto y deja la justificación
  sin adjunto; `DELETE /justifications/{id}` también elimina el objeto.
- Límite y TTL se configuran con `R2_MAX_UPLOAD_MB` y
  `R2_PRESIGN_EXPIRE_SECONDS`. El navegador nunca recibe credenciales de R2.

### Bloque 5 - enrolamiento facial (RF-04) y pipeline de visión

- `POST /students/{id}/faces` - 3–5 fotos **base64** (JSON `{"photos": [...]}`).
  Exige 1 rostro por foto y consistencia intra-alumno (cada foto frente al promedio de las demás ≥ 0.40);
  guarda el PROMEDIO normalizado en `face_embedding` y la portada en R2 con URL
  firmada (Bloque 13; si R2 está desactivado, cae a `storage/` local).
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

24 tests de autenticación corren contra la BD `fareas` real usando un usuario
temporal que se crea y elimina solo (no toca los datos del seed). Cubren login
con clave temporal, rate limit, `/me`, cambio forzado sin OTP, cambio voluntario
con OTP (cooldown, expiración, máximo de intentos e invalidación del token
viejo), recuperación completa, reset sin verificar y refresh tokens (rotación,
reuso, expiración, logout, logout-all y revocación por cambio de clave). La
suite completa (sin `test_vision.py`, que requiere el MP4 demo) se corre con
`pytest -q`.

### Bloque 6 - motor de asistencia (RF-21…RF-26)

- `GET /attendance/today?course=&room=&status=` - registros del día (vista `v_today_attendance`).
- `POST /sessions/{id}/manual-mark` - RF-21: marca manual del docente (solo en SUS grupos).
- `PATCH /attendance/{id}/rectify` - RF-15: rectifica el estado con motivo obligatorio (audit_log).
- `POST /sessions/{id}/close` - RF-26: cierre manual (admin); el automático corre cada 60 s
  (APScheduler) y genera faltas a matriculados sin registro + alertas DPI (RF-24).
- Clasificación RF-23 (**R2, Bloque 11**): `asistio` entre `inicio − apertura
  anticipada` y `inicio + tolerancia`; `tardanza` después de eso y hasta el **fin
  del bloque** (55 min tarde en 1 h = tardanza, no falta); `falta` la genera el cierre.

La suite (sin `test_vision.py`) es de **122 tests**. Cubre auth, catálogo,
cursos/choques/matrículas, calendario/parámetros/auditoría, motor de asistencia
y su API, WebSocket de dispositivos, dashboard/SSE/reportes, **importación OCR
de horarios, imágenes y nóminas (20)**, reglas del Bloque 11 y ciclos
(curso/filtros, choque entre ciclos y bloque histórico).
Todos son idempotentes: crean sus propios datos temporales y los limpian.
Los smokes de visión y enrolamiento viven en `test_vision.py` y se saltan solos
si faltan los modelos ONNX o el video demo.

## Recursos

El video de la "puerta del aula" vive en `back-fareas/resources/` (fuera de
git por peso, pero DENTRO del proyecto). `scripts/simulate_camera.py` lo usa
por defecto y los smokes de visión lo cargan vía `app/ai/resources.py`.

### Bloque 7 - WebSocket de dispositivos ESP32 (RF-25, RF-33, RF-35)

Protocolo en `ws://localhost:8000/api/v1/ws/devices?token=<DEVICE_TOKEN_SECRET>`:

1. `hello` → el `device_id` DEBE existir como ESP32 activo en `device`
   (close 4404 si no; 4401 con token inválido). Marca `is_online=TRUE`.
2. `heartbeat` cada 30 s → actualiza `last_heartbeat`; sin latidos por 90 s el
   scheduler lo marca fuera de línea (RF-35, visible en `GET /devices/status`).
3. El backend despacha veredictos Tabla 8: `{type:verdict, status, color,
   buzzer, seconds, message}` - el firmware enciende el NeoPixel + buzzer.

```bash
# Simular el nodo desde la PC (emula el LED en consola)
.venv/Scripts/python -u scripts/simulate_esp32.py esp32-lab305 --intervalo 5
```

### Bloque 8 - Dashboard en vivo y reportes (RF-13, RF-16)

- `GET /dashboard/summary` - tarjetas: asistencias/tardanzas/ausencias de hoy,
  % de ausentismo, cámaras y alertas DPI (`v_student_dpi` + `app_settings`).
- `GET /dashboard/live?access_token=<JWT>&room_id=` - **SSE** con los veredictos
  Tabla 8 del bucle de cámaras. EventSource no puede mandar cabeceras: el JWT
  va por query y se valida rol docente/admin. Ídem `/dashboard/live-room/{room_id}`.
- `GET /stats/hourly?day=` - marcas por hora de inicio de bloque (franja 07–20).
- `GET /stats/distribution?desde=&hasta=` - dona asistio/tardanza/falta/sin_registro
  (`sin_registro` = matriculados de sesiones cerradas sin marca).
- `GET /reports/attendance.xlsx|pdf?desde=&hasta=&course_id=` - RF-16 con
  encabezado institucional; el docente solo descarga SUS grupos (RF-21).

### Bloques 9, 14, 15 y 17 - Importación OCR de horarios, nóminas y malla curricular (RF-07)

- `POST /courses/import-pdf` - sube un **PDF digital, PDF escaneado o foto**
  (JPG/PNG/WEBP, ≤10 MB y 10 páginas; multipart, solo admin). Devuelve `tipo`
  (`pdf_texto`, `pdf_ocr` o `imagen`), páginas y bloques CANDIDATOS (curso,
  grupo, día, horas) con `confiable`, `nota`, `pagina`, `linea`, y sugerencias
  ya rellenadas de `teacher_id`, `room_id` y `curso_sugerido` (parecido por
  código/nombre cuando el curso aún no existe con ese código exacto).
  **No persiste nada**: es la pantalla de revisión del RF-07.
- `POST /courses/import-curriculum` (+ `/confirm`) - importa la **malla curricular**
  (PDF, foto o captura con un ciclo por columna o por sección): devuelve cada curso
  (`code`, `name`, `cycle`) con `confiable`, `nota`, `ya_existe`; `default_cycle`
  opcional para listas sin títulos. El `confirm` crea los nuevos y omite los que ya
  existen sin modificarlos. Solo admin.
- `POST /courses/import-pdf/confirm` - recibe la propuesta corregida,
  `semester_label` (periodo; por defecto el vigente), `cycle` (1–10),
  `teacher_id`/`room_id` por defecto y, opcionalmente, `teacher_id`/`room_id`
  por bloque (ambos pueden quedar en `null` si el horario no los trae). Crea
  los cursos que no existan, cursos/grupos/bloques con la validación RF-06/R9 y
  **todo o nada** (rollback ante choque). Reimportar el mismo archivo devuelve
  `omitidos` en vez de duplicar bloques. Un grupo solo admite un docente; el
  docente y el aula se completan luego con `PATCH /blocks/{id}`, y la sesión de
  asistencia solo se abre cuando ambos existen.
- `POST /students/import-preview` - sube una **nómina impresa en tabla**
  (PDF/foto) y `default_semester`; devuelve alumnos con código, DNI, nombres,
  correo (generado como `codigo@unamba.edu.pe` si falta), ciclo, `confiable`,
  `duplicado`, `errores` y la línea OCR. No crea nada.
- `POST /students/import-confirm` - recibe las filas corregidas y un
  `group_id` opcional. Crea las cuentas **fila por fila** (un duplicado no
  bloquea al resto), con clave temporal y correo RF-08; si se elige grupo,
  matricula con R8. Devuelve `creados`, `omitidos`, `matriculados` y errores por
  fila. Solo admin.

  > Límites: 10 MB, 10 páginas y 200 filas. Los grupos importados usan el
  > periodo indicado (R1, Bloque 11); las matrículas siguen exigiendo el
  > semestre vigente. OCR local: RapidOCR con modelos incluidos en el paquete;
  > manuscrito no soportado y las filas dudosas se marcan para corregir.

### Bloque 11 - reglas de negocio (R1…R15)

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
  con `fecha` opcional) - nunca genera faltas (R5).
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
  `rtsp_url` enmascarada en listados (completa en `GET /devices/{id}`). Al
  cambiar/restablecer la contraseña, `token_version` invalida los JWT viejos
  (401) y la respuesta entrega uno nuevo.
- **Biometría (R13, Ley 29733):** `POST /students/{id}/faces` exige `consent: true`;
  `DELETE /students/{id}/faces` borra embeddings y el objeto local/R2.
- **Feriados (R12):** `POST /holidays/range` (rango, omite fines de semana) y
  `POST /holidays/national?year=` (fijos + Semana Santa, ajustables).
- **Reportes:** `GET /reports/group-matrix.xlsx?group_id=` (alumnos × fechas con
  **A/T/F/FJ/-**) y `GET /reports/dpi-risk.xlsx?course_id=` (alerta/límite).

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
