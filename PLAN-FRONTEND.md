# PLAN DE IMPLEMENTACIÓN - FRONTEND FAREAS (Angular 21 + PrimeNG + Tailwind 4)

> Complemento de `PLAN-BACKEND.md` (bloques 1-9 ✅). El backend ya expone TODOS los
> endpoints necesarios; este plan conecta la interfaz a datos reales por bloques,
> cada uno terminando en algo navegable y verificable.
> Principio rector: **profesional y técnico, no empresarial**. Sin SSR, sin PWA,
> sin state managers externos (signals + services), sin librerías nuevas más allá
> de lo ya instalado (PrimeNG, Chart.js, Tailwind).

---

## 0. Estado actual del frontend (lo que YA existe y se reutiliza)

| ✅ Hecho | Detalle |
|---|---|
| Login completo RF-11/RF-12 | `features/auth/login`, `recover-password`, `change-password` + guards (`authGuard`, `loginGuard`, `mustChangePasswordGuard`) |
| Mi perfil con OTP (2026-10-22) | `features/profile` → cambio guiado de 3 pasos (clave actual → código al correo → nueva clave), contador de reenvío y persistencia del token nuevo |
| AuthService | signals `currentUser/isAuthenticated/isAdmin/isDocente/mustChangePassword`, rate-limit cliente, sin refresh tokens (coherente backend) |
| Interceptor 401 | `core/interceptors/auth.ts` → limpia sesión y manda a `/login?reason=session_expired` |
| Layout admin | `layouts/admin` con Sidebar + Header funcionales (menú PLANO: Dashboard, Asistencias) |
| Dashboard mock | 4 tarjetas, activity-feed con `setInterval`, hourly-chart, distribution-chart, student-list (todos con MOCK data) |
| Asistencia mock | `features/attendance` con tabla estática |
| Cursos y matrículas REALES (F2, 2026-10-12) | `features/courses` (lista de cursos + detalle con grupos y grilla semanal) y `features/enrollments` (cupo 40, retiro y transferencia) conectados a la API |
| Host global de toasts (2026-10-12) | `app.html` incluye `<p-toast>`; sin él, TODOS los `toast.add()` de la app (errores 409 incluidos) quedaban invisibles |
| Build OK | `ng build --configuration development` pasa; `dist/fareas` generado |

**Stack fijo:** Angular 21 (standalone + signals + OnPush), PrimeNG 20, Tailwind 4,
Chart.js 4, material-symbols/akar-icons ya en uso.## 1. Decisiones definitivas (respondidas por el usuario)

1. **~~El rol ESTUDIANTE no entra al panel~~ → REVISADO: el estudiante SÍ entra a la app**:
   el backend ya expone `GET /attendance/me` (historial personal, solo rol estudiante) y
   el estudiante recibirá su propia vista "Mis asistencias" (Responsive list con curso,
   grupo, estado, fecha, método y motivo de rectificación RF-15). El panel admin/docente
   sigue restringido por `authGuard`/`roleGuard`; las alertas por correo (RF-24) se mantienen.
   **Estado frontend:** este bloque NO se ha implementado aún; queda documentado aquí para
   insertarse como sub-bloque de F3b (ver §4 F3b).
2. **Hardware al final (F7)**: cámara Hikvision + ESP32 se conectan cuando el
   frontend puede MONITOREARLOS (RF-35) — así cada paso se verifica desde la UI.
3. **Sidebar agrupado con submenús** (secciones colapsables), con visibilidad por rol.
4. **Backend mínimo extra aprobado**: `GET /attendance/sessions-today`
   (sesiones abiertas de hoy con session_id/curso/grupo/aula/estado) para el modal
   de marca manual RF-21 — **✅ YA IMPLEMENTADO EN EL BACKEND** (Bloque 6b del
   PLAN-BACKEND, excluye cerradas; el frontend ya lo consume en la pantalla
   Asistencias con el modal RF-21 pre-integrado).
5. **Rate limit de login en el backend**: añadido en el Bloque 6b (5 fallos/IP/min → 429;
   login correcto limpia). El rate limit del cliente (`auth-rate-limit.ts`) se mantiene
   como primera capa UX.
6. **`/attendance/me` (estudiante)**: endpoint YA IMPLEMENTADO en el backend (Bloque 6b);
   su pantalla en el frontend queda para F3b (ver §4).

## 2. Estructura de rutas objetivo (Bloque F1 las crea; F2-F6 las llenan)

```
/admin                    → AdminLayout (authGuard + roleGuard admin|docente)
  /dashboard              → Dashboard REAL (F5)          [admin, docente]
  /attendance             → Asistencias REAL (F3)        [admin, docente]
  /courses                → Cursos y grupos + bloques (F2) [admin CRUD; docente lectura]
  /enrollments            → Matrículas por grupo (F2)     [admin CRUD; docente lectura]
  /teachers               → Docentes (F2)                 [admin]
  /students               → Estudiantes + estado facial (F2/F4) [admin; docente lee]
  /rooms                  → Aulas (F2)                    [admin]
  /devices                → Dispositivos + monitoreo RF-35 (F2/F5) [admin]
  /calendar/holidays      → Feriados (F3)                 [admin CRUD; docente lee]
  /calendar/justifications→ Justificaciones (F3)          [admin CRUD; docente lee]
  /calendar/settings      → Parámetros RF-34 (F3)         [admin]
  /faces                  → Enrolamiento facial (F4)      [admin]
  /imports                → Importar horario PDF RF-07 (F6) [admin]
  /reports                → Reportes Excel/PDF (F6)       [admin, docente]
  /audit                  → Bitácora RF-32 (F6)           [admin]
/login  /auth/recover  /auth/change-password   → (ya existen, solo retoques visuales)
```

Guard nuevo en F1: `roleGuard` leyendo `data: { roles: ['admin'] }` de la ruta;
el menú del sidebar filtra con la MISMA matriz (una sola fuente de verdad:
`core/constants/nav.ts`).

## 3. Menú del sidebar (agrupado, con roles)

Fuente única: `core/constants/nav.ts` → `NavItem { label, route, icon, roles, children? }`.
El sidebar actual (`layouts/admin/components/sidebar`) se extiende: grupos colapsables
(uno abierto a la vez), badge opcional (p. ej. alertas DPI en Dashboard), mismo estilo.

**ADMIN ve:**

| Grupo | Ítem (ruta) | Icono |
|---|---|---|
| — | Dashboard (`/dashboard`) | `material-symbols:dashboard-outline` |
| — | Asistencias (`/attendance`) | `material-symbols:fact-check-outline` |
| Académico ▾ | Cursos y grupos (`/courses`) | `material-symbols:menu-book-outline` |
| | Matrículas (`/enrollments`) | `material-symbols:how-to-reg-outline` |
| Catálogo ▾ | Docentes (`/teachers`) | `material-symbols:person-outline` |
| | Estudiantes (`/students`) | `material-symbols:school-outline` |
| | Aulas (`/rooms`) | `material-symbols:meeting-room-outline` |
| | Dispositivos (`/devices`) | `material-symbols:videocam-outline` |
| Calendario ▾ | Feriados (`/calendar/holidays`) | `material-symbols:event-busy-outline` |
| | Justificaciones (`/calendar/justifications`) | `material-symbols:medical-information-outline` |
| | Parámetros (`/calendar/settings`) | `material-symbols:tune` |
| Herramientas ▾ | Enrolamiento facial (`/faces`) | `material-symbols:face-retouching-natural` |
| | Importar horario (PDF) (`/imports`) | `material-symbols:upload-file-outline` |
| | Reportes (`/reports`) | `material-symbols:description-outline` |
| | Bitácora (`/audit`) | `material-symbols:history-toggle-off-outline` |

**DOCENTE ve:** Dashboard · Asistencias · Académico (Cursos, Matrículas — solo lectura)
· Calendario (Feriados, Justificaciones — lectura) · Herramientas (Reportes).
Los botones de creación/edición se ocultan con `@if (auth.isAdmin())` en las vistas
compartidas (el backend ya rechaza con 403 igualmente: doble capa).

---

## 4. Bloques de implementación (cada uno termina verificable)

### F0-F1 - Infraestructura de datos + navegación (½ día)
- [ ] `core/api/`: `api-url.ts` (dev: `environment.apiUrl`; prod: `/api/v1` relativo),
  `page.ts` (tipo `Page<T>` idéntico al backend), `params.ts` (serializa `?page=&page_size=&q=`).
- [ ] `core/services/` genéricos por módulo: `catalog-api.ts` (rooms/devices/teachers/students
  con `Page<T>`), `courses-api.ts`, `calendar-api.ts` — HttpClient tipado, sin estado global
  (cada página recarga; PLAN §7: sin NgRx).
- [ ] UI kit compartido: `shared/components/` → `page-header`, `data-table` (ya existe:
  ampliar a `Page<T>` + paginador PrimeNG), `confirm-dialog` (PrimeNG ConfirmationService),
  `toasts` (MessageService global), `empty-state`, `skeleton-table`.
- [ ] `roleGuard` + rutas hijas de `/admin` con `data.roles` (rutas creadas apuntando a
  placeholders "En construcción" salvo las existentes).
- [ ] Sidebar agrupado con `nav.ts` + submenús colapsables + roles.
- **Entregable:** login → panel con menú completo por rol; rutas nuevas navegan a placeholders.

### F2 - Catálogos y carga académica (1-1.5 días) - RF-02…RF-06, RF-22, RF-35
- [ ] **Aulas** `/rooms`: tabla paginada + crear/editar (dialog) — `GET/POST /rooms`, `PATCH /rooms/{id}`.
- [ ] **Docentes** `/teachers`: tabla + alta (dialog: nombre, email, DNI, WhatsApp) — `GET/POST /teachers`;
  botón "Reenviar clave" → `POST /accounts/{id}/send-temp-password`; editar → `PATCH /accounts/{id}`.
- [ ] **Estudiantes** `/students`: tabla + alta (incluye `code` y `semester`) — `GET/POST /students`;
  columna "Rostro" con badge Enrolado/Sin rostro (F4 lo conecta a `GET /students/{id}/faces`).
- [ ] **Dispositivos** `/devices`: tabla + alta (tipo cámara exige `rtsp_url`) — `GET/POST /devices`,
  `PATCH /devices/{id}`; **pestaña "Monitoreo" RF-35**: tarjetas por aula con estado en línea
  (verde/gris) desde `GET /devices/status` (público) con auto-refresh cada 30 s.
- [ ] **Cursos y grupos** `/courses`: lista de cursos (`GET/POST /courses`) → detalle de curso con
  sus grupos (`GET /courses/{id}/groups?semester=` — **Bloque 11: cada grupo trae `semester_label`,
  `capacity` y `enrolled_count`**), crear grupo (docente+aula+**cupo, 40 por defecto**: selects de
  `/teachers` y `/rooms`) → detalle de grupo con BLOQUES horarios (grid semanal LUN-DOM,
  crear/patch/delete con detección de choque RF-06 mostrando el 409 del backend como toast).
- [ ] **Matrículas** `/enrollments`: selector curso→grupo (`GET /courses` + `GET /courses/{id}/groups`)
  + listar/alta/quitar alumnos (`GET/POST/DELETE /groups/{id}/students`, autocomplete de estudiantes).
  **Bloque 11 (R8):** el alta puede responder 409 con mensajes claros ("Grupo lleno 40/40",
  "ya está matriculado en el grupo B", "el horario se cruza con …"); el listado trae
  `withdrawn_at` (retirados) y `has_face`; hay **transferencia** entre grupos del mismo curso:
  `POST /groups/{id}/students/{student_id}/transfer` con `{destino_group_id}`.
  La pestaña de parámetros usa `GET /settings/semesters` para el selector de semestre.
- **Entregable:** admin puede montar la malla completa desde la UI sin pgAdmin; docente la ve.

### F2 - Estado real (actualizado al 2026-10-12) - ✅ LISTO
- [x] **Cursos** `/courses`: lista paginada con búsqueda + alta de curso (código 3-20, nombre);
  acción "Grupos y horario" que navega al detalle (ruta RELATIVA, el panel vive bajo `/admin`).
- [x] **Detalle de curso** `/courses/:courseId`: selector de semestre (por defecto el vigente,
  tomado de `GET /settings` y persistido en la URL), tarjetas de grupo con **cupo X/40**
  (barra con umbral verde/ámbar/rojo), docente, aula y semestre; alta de grupo (código, cupo
  con 40 por defecto, selects de docente y aula); baja lógica del grupo con `app-modal-delete`.
- [x] **Grilla semanal de bloques** (LUN–DOM): chips `HH:MM–HH:MM`, alta por columna (día
  preseleccionado + hora de inicio "inteligente" tras el último bloque del día, 1 h o 2 h) y
  borrado por bloque. El **409 de choque (RF-06)** se muestra como toast con el mensaje del
  backend y el diálogo permanece abierto para corregir la hora.
- [x] **Matrículas** `/enrollments`: selector semestre → curso → grupo (con cupo y aula en la
  etiqueta), tarjeta resumen del grupo (docente, aula, cupo con `activos()/capacity` y aviso
  "grupo lleno"), tabla de alumnos con badge **Enrolado/Sin rostro** (`with_face=1`), estado
  Activo/Retirado y acciones: **matricular** (buscador de estudiantes contra el servidor con
  retardo de 250 ms), **retirar** (dialog con aviso de historial), **reactivar** y **transferir**
  a otro grupo del mismo curso (solo grupos con cupo libre).
- [x] **Reglas R8 verificadas en navegador contra la BD real**: cupo, "ya está matriculado en el
  grupo A de ISA903; usa la transferencia" (un grupo activo por curso), "el horario se cruza con
  otro curso del alumno: ISA901 (grupo A)", retiro (borra si no hay registros; el cupo baja a
  5/40) y transferencia (la matrícula de origen queda `withdrawn_at` y se crea la del destino).
- [x] **Arreglos de shell** (bugs reales encontrados al verificar): host global `<p-toast>` en
  `app.ts`/`app.html` (antes ningún toast se veía), `isActive()` del sidebar marca también las
  subrutas (`/admin/courses/3` resalta "Cursos y grupos") y el helper `extractDetail` pasó a
  `shared/utils/api-error.ts` (re-exportado desde `rooms.ts` para no romper imports).

### F3 - Asistencia y calendario (1 día) - RF-09, RF-10, RF-15, RF-21, RF-26, RF-34
- [ ] **Backend (~30 min, aprobado):** `GET /attendance/sessions-today` →
  `[{session_id, course_code, course_name, group_code, room_code, weekday, start_time, end_time,
  status, total_marcas}]` (sesiones de hoy abiertas+cerradas del docente o todas para admin).
- [ ] **Asistencias** `/attendance`: tabla en vivo de HOY desde `GET /attendance/today` con filtros
  curso/aula/estado (refresh manual + botón); **modal marca manual RF-21**: seleccionar sesión
  (de `sessions-today`) → estudiante (solo matriculados del grupo) → estado → `POST /sessions/{id}/manual-mark`;
  **rectificar RF-15**: acción de fila con dialog motivo → `PATCH /attendance/{id}/rectify`;
  botón "Cerrar sesión" (admin) → `POST /sessions/{id}/close` con resumen de faltas.
- [ ] **Bloque 11 (backend ya listo):**
  - **Día sin clase / paro:** `POST /sessions/{id}/cancel` y `POST /blocks/{id}/cancel-day`
    (body `{reason, fecha?}`; admin también pre-cancela fechas futuras).
  - **Sesiones por revisar (R4):** `GET /attendance/sessions-review` (cerradas con cero marcas;
    la cámara pudo caerse) → botón por fila: `POST /sessions/{id}/resolve-review`
    `{action: confirmar_faltas | cancelar, reason?}` (cancelar exige motivo).
  - **Justificar UNA falta:** acción de fila → `PATCH /attendance/{id}/justify` `{reason}`
    (solo admin/docente; el estado de la fila pasa a "Falta justificada", FJ).
  - **Plazo de rectificación:** el backend responde 403 a docentes fuera de los 7 días
    (`rectify_days`); la UI puede ocultar la acción en filas antiguas y mostrar el motivo.
- [ ] **Feriados** `/calendar/holidays`: lista + alta/baja — `GET/POST /holidays`, `DELETE /holidays/{id}`;
  **Bloque 11:** botón "Cargar feriados nacionales del año" → `POST /holidays/national?year=`
  (o body `{year}`) y "Paro por rango" → `POST /holidays/range` `{desde, hasta, descripcion,
  omitir_fines_de_semana}` → chip con `{creados, omitidos, sesiones_canceladas}`.
- [ ] **Justificaciones** `/calendar/justifications`: lista filtrable por alumno + alta
  (rango fechas, motivo, curso opcional, documento URL) — `GET/POST /justifications`, `DELETE /justifications/{id}`.
  **Bloque 11 (R6):** la respuesta de alta trae `faltas_afectadas` (mostrarlo en el toast) y el
  docente está obligado a elegir curso; eliminar revierte las faltas (confirmar con dialog).
- [ ] **Parámetros** `/calendar/settings`: formulario semestre/bloque/tolerancia/**ventana de
  apertura (early_open_minutes), rectify_days, dpi_min_sessions y fechas del semestre
  (semester_start/end)** — `GET/PATCH /settings` (aviso: "aplica a sesiones siguientes, nunca
  retroactivo" RF-34; validación cliente: aviso < límite; inicio < fin).
- **Entregable:** el flujo completo de un día lectivo se opera 100% desde la UI.

### F3 - Estado real (actualizado al 2026-10-12) - ✅ LISTO
- [x] **Asistencias** `/attendance`: tabla en vivo de HOY (`GET /attendance/today` +
  `sessions-today`, auto-refresh 60 s, filtro `?status=` y buscador por estudiante/curso con
  `app-ui-input`), **modal marca manual RF-21** (solo matriculados del grupo),
  **rectificación RF-15** (diálogo con motivo ≥5 → `PATCH /attendance/{id}/rectify`),
  **justificación puntual R6** (`PATCH /attendance/{id}/justify` → la fila pasa a **FJ**)
  y tarjeta de **sesiones abiertas** con **cierre RF-26** (admin), cancelación R5 y
  **sesiones por revisar R4** (confirmar faltas / cancelar la clase con motivo obligatorio).
- [x] **Feriados** `/calendar/holidays`: lista por año + alta/baja, **"Cargar feriados
  nacionales"** (`POST /holidays/national`) y **"Paro por rango"** (`POST /holidays/range`
  con chip de creados/omitidos/sesiones canceladas).
- [x] **Justificaciones** `/calendar/justifications`: tabla filtrable por alumno y curso, alta
  en diálogo (rango, motivo, curso obligatorio para docente, documento URL) con
  `faltas_afectadas` en el toast y baja que revierte las faltas.
- [x] **Parámetros** `/calendar/settings`: formulario completo (semestre y fechas, bloques,
  tolerancia, ventana de apertura, días de rectificación, umbral facial y % de DPI) con aviso
  "aplica a sesiones siguientes, nunca retroactivo" (RF-34), validación cliente y botón
  deshabilitado mientras no haya cambios; `PATCH /settings` ✅.
- [x] **Verificado en navegador contra la BD real** (fixture temporal `ZZF301` con una sesión
  abierta y dos por revisar): marca manual, rectificación, justificación, confirmar faltas,
  cerrar sesión y cancelar la clase; feriados nacionales y por rango, alta de justificación y
  guardado de parámetros (todos con su `POST/PATCH` en 200/201).
- [x] **Bugs reales corregidos al verificar**: `attendance.ts` usaba `<app-ui-input>` sin
  importarlo — con `CUSTOM_ELEMENTS_SCHEMA` no fallaba el build pero lanzaba `NG01203` en runtime
  y el buscador no se renderizaba; y Justificaciones pedía `page_size=200` cuando el backend
  limita a 100 (422 → el selector de cursos quedaba vacío).

### F3b - "Mis asistencias" del ESTUDIANTE (nuevo, ½ día) - RF-22/RF-24 con vista propia
> Decisión 1 revisada: el estudiante SÍ entra a la app. El backend YA expone
> `GET /attendance/me` (Bloque 6b del PLAN-BACKEND: solo rol estudiante, filtros
> ?desde=&hasta=, devuelve curso, grupo, estado, marked_at, method y correct_reason).
- [ ] Ruta `​/me` (o `/my-attendance`) FUERA de `/admin` (otro guard: solo rol estudiante;
  el panel admin/docente sigue con roleGuard) con layout propio simple.
- [ ] Pantalla: lista de asistencias del alumno (curso, grupo, fecha/franja, badge de estado
  asistio/tardanza/falta con colores Tabla 8, método facial/manual) + filtro de rango de fechas.
  **Bloque 11:** la respuesta trae `is_justified` → badge propio para la **falta justificada (FJ)**
  (no cuenta para el 30 %); añadir una tarjeta de **DPI por curso** con `GET /attendance/me/dpi`
  (porcentaje, nivel alerta/límite, sesiones planificadas y faltas restantes).
- [ ] Mostrar `correct_reason` si la marca fue rectificada (RF-15 visible para el alumno).
- [ ] El estudiante no puede navegar a `/admin` (authGuard y roleDocente ya lo bloquean;
  verificar la redirección de login para rol estudiante → `/me` y no a `/admin/dashboard`).
- **Entregable:** el estudiante entra con su cuenta del BD (código o correo), ve SU historial
  y sus alertas DPI siguen llegando por correo (RF-24) sin cambio en el backend.

### F3c - "Mi perfil": cambio de contraseña con OTP (2026-10-22) - **✅ LISTO**
> El backend ya expone `/auth/change-password/otp` → `/otp/verify` →
> `/change-password` (PLAN-BACKEND, Bloque 3b). La UI mantiene el estilo del
> sistema: tarjeta blanca `rounded-2xl border-gray-100`, azul primario, iconos
> Material Symbols, `app-ui-input`/`app-ui-button`/`app-ui-alert`.
- [x] **Paso 1 - Identidad:** contraseña actual + botón "Enviar código". Muestra
  un aviso de que el código llegará al correo institucional.
- [x] **Paso 2 - Código:** correo **enmascarado**, input de 6 dígitos
  (`inputmode=numeric`, `maxlength=6`, `autocomplete=one-time-code`, solo dígitos
  al pegar), botón "Verificar código", reenvío con **contador de 60 s** y enlace
  "Usar otra contraseña actual".
- [x] **Paso 3 - Nueva clave:** nueva contraseña + confirmación (mín. 8), valida
  que coincidan y que no sea igual a la actual; botón "Actualizar contraseña".
- [x] Barra de progreso + `aria-current="step"`, `aria-live="polite"` para
  errores/éxito, foco automático al cambiar de paso, `aria-invalid` en el input,
  y `motion-reduce` en transiciones.
- [x] Manejo de errores del backend: 400 (clave/código), 429 (cooldown o intentos
  agotados → vuelve al paso 1), OTP vencido (vuelve al paso 2 para reenviar).
- [x] Al éxito: alerta "Contraseña actualizada", formulario limpio y vuelta al
  paso 1. `AuthService.changePassword` guarda el `access_token` nuevo porque
  `token_version` invalidó el anterior.
- [x] Spec `profile.spec.ts`: recorre los 3 pasos con `HttpTestingController` y
  verifica cuerpos de petición, correo enmascarado, transición y éxito.
- **Archivos:** `features/profile/profile/profile.{ts,html,spec.ts}`,
  `core/services/auth/auth.ts`, `core/models/user.ts`,
  `shared/components/ui-input/ui-input.{ts,html}`.
- **Verificación:** `npm run build` OK y `npm test -- --watch=false` OK.

### F4 - Enrolamiento facial (½-1 día) - RF-04, RF-20
- [ ] Página `/faces`: buscar estudiante → `GET /students/{id}/faces` muestra estado actual
  (enrolado sí/no, foto, fecha); flujo de captura: **webcam** (`navigator.mediaDevices.getUserMedia`,
  botón capturar ×N) O **subir archivos** (input multiple); client-side: comprimir a JPEG ~640px,
  convertir a base64 → `POST /students/{id}/faces` con `{photos: [...], consent: true}`.
  **Bloque 11 (R13, Ley 29733):** obligatorio un **checkbox de consentimiento** antes de enviar
  (sin `consent: true` el backend responde 422) y acción "Eliminar rostro" (admin) →
  `DELETE /students/{id}/faces` con dialog de confirmación (borra embeddings y foto).
- [ ] Manejo de errores del validador facial: 1 rostro por foto, consistencia ≥0.55,
  duplicado → mensajes claros del backend en toasts.
- [ ] En `/students`: badge de enrolamiento + acción directa "Enrolar rostro".
- **Entregable:** enrolar a un alumno desde la webcam y verlo identificado en el video demo
  (`scripts/simulate_camera.py`) sin tocar la BD a mano.

### F5 - Dashboard en vivo (1 día) - RF-13, RF-35, PLAN §5
- [ ] `DashboardApi`: `GET /dashboard/summary` → las tarjetas reales (asistencias/tardanzas/
  ausencias con %, cámaras activas, alertas DPI) con auto-refresh 30 s. **Bloque 11:** la tarjeta
  DPI distingue `en_riesgo` (≥ 20 %) de `alertas_dpi` (> 30 %, inhabilitación) y hay un
  **banner/contador `sessions_to_review`** que enlaza a la pantalla de sesiones por revisar (F3).
- [ ] **Activity-feed con SSE real** (reemplaza el `setInterval`):
  `new EventSource(\`${api}/dashboard/live?access_token=${token}&room_id=...\`)`
  evento `verdict` → feed con nombre/código/similitud/veredicto (colores Tabla 8);
  `onerror` → reconexión con backoff y banner "En vivo / Reconectando…";
  cerrar en `onDestroy` (sin fugas).
- [ ] **hourly-chart**: `GET /stats/hourly` (serie total por hora, misma estética Chart.js actual,
  selector Hoy con `day=` para Ayer).
- [ ] **distribution-chart**: `GET /stats/distribution` (dona con asistio/tardanza/falta/sin_registro).
- [ ] **student-list**: consume `GET /attendance/today` (ya con F3).
- [ ] Tarjeta "Cámaras activas" enlaza a `/devices` (pestaña Monitoreo RF-35).
- **Entregable:** el dashboard refleja la BD y el feed muestra los veredictos REALES del
  bucle de cámaras (verificable con `simulate_camera.py` + `simulate_esp32.py` corriendo).

### F6 - Reportes, importación PDF y bitácora (½-1 día) - RF-16, RF-07, RF-32
- [ ] **Reportes** `/reports`: filtros desde/hasta + curso (opcional) + botones
  "Excel" / "PDF" → `GET /reports/attendance.xlsx|pdf` con `responseType: 'blob'` +
  descarga vía `URL.createObjectURL` (respeta el `filename` del Content-Disposition);
  docente ve solo SUS grupos (el backend ya filtra).
  **Bloque 11:** dos reportes adicionales — "Registro de asistencia" del grupo
  (`GET /reports/group-matrix.xlsx?group_id=` → matriz alumnos × fechas con **A/T/F/FJ/—**)
  y "Riesgo DPI" (`GET /reports/dpi-risk.xlsx?course_id=` → alumnos en alerta/límite con
  faltas restantes). El estado `FJ` = falta justificada (no cuenta para el 30 %).
- [ ] **Importar horario** `/imports` (RF-07, 2 pasos): subir PDF → tabla editable de la
  previsualización (`POST /courses/import-pdf`) con filas ambiguas resaltadas (chip "Ambiguo"
  + `nota`), select de docente y aula → confirmar → `POST /courses/import-pdf/confirm`
  → resumen de creados (cursos/grupos/bloques) y manejo del 409 de choque (todo-o-nada).
- [ ] **Bitácora** `/audit` (admin): tabla paginada `GET /audit-log` con filtros
  action/entity/entity_id/actor/**actor_role**/since (backend ya los soporta) + visor de
  old/new_value (JSON); la respuesta trae `actor_name` y `actor_role` para la columna "Quién".
  **Bloque 11:** aquí se ven las acciones nuevas (sesión cancelada/revisada, justificación,
  matrícula retirada/transferida, rostro eliminado, consentimiento, feriado por rango).
- **Entregable:** tesis puede mostrar: subir PDF real → propuesta → confirmar → bloques en horario.

### F7 - DISPOSITIVOS REALES: cámara + ESP32 (1-1.5 días) — guía completa de armado
> Orden: primero la CÁMARA (solo configuración de red, sin soldar nada),
> luego el ESP32 (hardware). Todo queda monitoreado en `/devices` (RF-35, F2).

#### 7A. Cámara Hikvision PoE (RF-17) — SOLO software y red
**¿Se descarga el programa del link que me pasaste (iVMS-4200)?** SÍ conviene, pero NO
es estrictamente obligatorio. Lo imprescindible es **SADP Tool** (viene dentro de iVMS-4200
o se descarga aparte, búsqueda "SADP tool Hikvision"): es el que DESCUBRE la cámara en la red,
la ACTIVA (primer uso: define usuario/contraseña) y le pone IP fija. iVMS-4200 añade vista
en vivo y gestión cómoda desde Windows — recomendado para la tesis (capturas de pantalla).

1. **Cableado:** cámara → puerto **PoE+** del TP-Link LS108GP con cable Cat6 (datos+energía
   en un solo cable). PC también al switch. La cámara y tu PC en la MISMA red.
2. **Instalar SADP/iVMS-4200** en Windows y abrir: la cámara aparece como "Inactive".
3. **Activar:** definir contraseña fuerte (GUÁRDALA: va dentro del `rtsp_url`) — p. ej. `Fareas2026*`.
4. **IP fija** desde SADP: p. ej. `10.14.5.11` (máscara/gateway de tu red) → la cámara reinicia.
5. **Verificar web:** navegador a `http://10.14.5.11` → login admin → ver imagen en vivo.
6. **URL RTSP** (la que va a la BD): SUB-STREAM recomendado (menos CPU):
   `rtsp://admin:Fareas2026*@10.14.5.11:554/Streaming/Channels/102`
7. **Probar sin backend:** `python scripts/test_rtsp.py "rtsp://..."` → muestra 1 frame.
8. **Registrar en BD** (ya hay 6 cámaras del seed; actualiza la del aula):
   `UPDATE device SET rtsp_url='rtsp://...', ip_address='10.14.5.11' WHERE device_key='cam-lab305';`
9. **Verificación final:** backend arriba → `/devices` Monitoreo la muestra EN LÍNEA tras el
   primer frame; persona enfrente de la cámara → marca en `/attendance` + LED del ESP32 (7B).

#### 7B. ESP32 + anillo NeoPixel 16 + buzzer (RF-25, RF-27…RF-29, RF-33)
**Materiales:** ESP32 DevKit (30 pines) · anillo WS2812B 16 LEDs · buzzer ACTIVO 5 V ·
resistencia 330–470 Ω · condensador electrolítico 1000 µF (≥6.3 V) · jumpers hembra-hembra ·
cable USB con DATOS · protoboard (opcional).

**Cableado (con el ESP32 DESCONECTADO de USB):**

| Del | Al | Nota |
|---|---|---|
| Anillo 5V (VCC) | VIN/5V del ESP32 | alimentado por el USB |
| Anillo GND | GND del ESP32 | común |
| Anillo DIN | **GPIO 13** vía resistencia 330–470 Ω | en serie, acorta el cable de datos |
| Condensador 1000 µF | entre 5V y GND del anillo | banda larga (++) a 5V — protege picos |
| Buzzer + | **GPIO 26** | ⚠️ actualizado en el Bloque 11: GPIO 12 es pin de ARRANQUE del ESP32 y colgaba el boot. Si el buzzer es de 5 V "duro": transistor 2N2222 (base 1 kΩ a GPIO26) |
| Buzzer − | GND | |

**Software en la PC:**
1. **Arduino IDE 2.x** (arduino.cc). Boards Manager → URL de Espressif:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json` → instalar
   **"esp32 by Espressif Systems"**. Placa: **DOIT ESP32 DEVKIT V1**. Si el puerto COM no
   aparece: driver CP210x (Silicon Labs).
2. **Library Manager:** instalar `Adafruit NeoPixel` y `WebSockets` (de Markus Sattler / Links2004).

**Firmware (`fareas_nodo.ino`)** — habla EXACTAMENTE el protocolo del backend:

```cpp
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <Adafruit_NeoPixel.h>

const char* WIFI_SSID = "TU_RED";
const char* WIFI_PASS = "TU_CLAVE";
// token = DEVICE_TOKEN_SECRET del .env del backend
const char* WS_HOST = "192.168.1.XX";   // IP de la PC con el backend
const uint16_t WS_PORT = 8000;
const char* WS_PATH = "/api/v1/ws/devices?token=COPIA_DEVICE_TOKEN_SECRET";
const char* DEVICE_ID = "esp32-lab305";  // device.device_key en la BD

#define LED_PIN 13
#define BUZZ_PIN 26   // Bloque 11: GPIO12 es pin de arranque (bootstrapping)
#define LED_COUNT 16

Adafruit_NeoPixel ring(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);
WebSocketsClient ws;
uint32_t lastBeat = 0;

void mostrar(const char* color, int beeps, int ms, int segundos) {
  uint32_t c = ring.Color(0,0,0);
  if (!strcmp(color,"verde"))    c = ring.Color(0,180,0);
  if (!strcmp(color,"amarillo")) c = ring.Color(220,140,0);
  if (!strcmp(color,"rojo"))     c = ring.Color(200,0,0);
  if (!strcmp(color,"azul"))     c = ring.Color(0,60,200);
  ring.fill(c); ring.show();
  for (int i=0;i<beeps;i++){ digitalWrite(BUZZ_PIN,HIGH); delay(ms); digitalWrite(BUZZ_PIN,LOW); delay(120); }
  delay(segundos*1000);
  ring.clear(); ring.show();                 // vuelve a reposo
}

void onEvent(WStype_t type, uint8_t* payload, size_t len) {
  if (type == WStype_CONNECTED) {
    enviarHello();                            // Bloque 11: el hello va AQUÍ
  }
  if (type == WStype_TEXT) {
    StaticJsonDocument<384> doc;
    if (deserializeJson(doc, payload, len)) return;
    if (!strcmp(doc["type"],"verdict"))
      mostrar(doc["color"], doc["buzzer"]=="beep_2"?2:doc["buzzer"]=="beep_1"?1:4,
              doc["buzzer"]=="tono_denegado"?600:120, doc["seconds"]|3);
    Serial.printf("[WS] %s\n", (char*)payload);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZ_PIN, OUTPUT);
  ring.begin(); ring.setBrightness(60); ring.clear(); ring.show();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  ws.begin(WS_HOST, WS_PORT, WS_PATH);
  ws.onEvent(onEvent);
  ws.setReconnectInterval(5000);
}

void enviarHello() {  // Bloque 11: al CONECTAR, no en setup()
  String hello = String("{\"type\":\"hello\",\"device_id\":\"") + DEVICE_ID + "\",\"mac\":\"" + WiFi.macAddress() + "\"}";
  ws.sendTXT(hello);                          // presentación RF-33
}

void loop() {
  ws.loop();
  if (millis() - lastBeat > 30000) {          // latido cada 30 s
    lastBeat = millis();
    ws.sendTXT("{\"type\":\"heartbeat\"}");
  }
}
```
(Añadir `#include <ArduinoJson.h>` — instalar también la librería **ArduinoJson**.)

**Registro y red:**
- El device_key DEBE existir: el seed trae `esp32-lab305` (o créalo en `/devices` → tipo ESP32).
- **Firewall de Windows** para que el ESP32 alcance tu API (requiere permiso del usuario;
  en F7 se pide aprobación y se ejecuta):
  `netsh advfirewall firewall add rule name="Fareas API 8000" dir=in action=allow protocol=TCP localport=8000`
- **Checklist de verificación:** 1) `simulate_esp32.py` verde/beep en consola; 2) grabar el
  ESP32 y ver `hello_ack` en el monitor serie; 3) `GET /devices/status` lo muestra EN LÍNEA
  (RF-35); 4) video/entrada con alumno enrolado → LED verde + 1 beep y marca en `/attendance`;
  5) desconectar USB → EN LÍNEA pasa a FUERA DE LÍNEA en ≤150 s (90 latido + 60 scheduler).
- **Tono completo (Tabla 8):** verde+beep_1 · amarillo+beep_2 · rojo+tono_denegado (600 ms)
  · azul = animación de reposo **sin beeps** (el backend manda `buzzer:"ninguno"`; el sketch
  hace fade simple).
- **Red (Bloque 11):** reservar **IP fija por DHCP** para la PC del backend (la IP del ESP32
  cambia de red; el `WS_HOST` del firmware debe seguir siendo válido) y usar WiFi de **2.4 GHz**
  (el ESP32 no soporta 5 GHz).

### F8 - Producción y demo de tesis (½ día) - (par con Bloque 10 del backend)
- [ ] `environment.prod.ts` con `apiUrl: '/api/v1'` (mismo origen, sin CORS).
- [ ] `ng build --configuration production` → `dist/fareas/browser`.
- [ ] Backend: montar los estáticos en `main.py` (`app.frontend()` pendiente del Bloque 10:
  StaticFiles + fallback a `index.html` para rutas Angular) + `fastapi run` con
  `ENVIRONMENT=production` (sin /docs).
- [ ] Acceso externo: **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:8000`)
  → URL pública para la sustentación.
- [ ] **Guion de demo (10 min):** login admin → parámetros → crear curso/grupo/bloque (F2) →
  importar PDF de matrícula (F6) → matricular (F2) → enrolar rostro por webcam (F4) →
  cámara/ESP32 en la puerta (F7) → dashboard en vivo con SSE (F5) → marca manual y
  rectificación (F3) → reporte PDF (F6) → bitácora (F6).

---

## 5. Referencia rápida API ↔ frontend ↔ rol

| Endpoint | Lo usa (pantalla) | Rol |
|---|---|---|
| `POST /auth/login` · `GET /auth/me` · `POST /auth/change-password` · `/auth/change-password/otp` + `/otp/verify` · `/auth/recover/*` | Login/recuperación/Mi perfil (YA) | todos |
| `GET/POST /rooms` · `PATCH /rooms/{id}` | Aulas (F2) | A admin · L docente |
| `GET/POST /devices` · `PATCH /devices/{id}` · `GET /devices/status` | Dispositivos + Monitoreo RF-35 (F2/F5) | A admin · status público |
| `GET/POST /teachers` · `GET/POST /students` · `GET/PATCH /accounts/{id}` · `POST /accounts/{id}/send-temp-password` | Catálogo de personas (F2) | A admin · L docente |
| `GET/POST /courses` · `GET/POST /courses/{id}/groups` · `GET/POST /groups/{id}/blocks` · `PATCH/DELETE /blocks/{id}` · `DELETE /groups/{id}` | Cursos y grupos (F2) | A admin · L docente |
| `GET/POST/DELETE /groups/{id}/students` · `POST /groups/{id}/students/{sid}/transfer` · `GET /settings/semesters` | Matrículas con reglas R8 (F2) | A admin · L docente |
| `GET /attendance/today` · `POST /sessions/{id}/manual-mark` · `PATCH /attendance/{id}/rectify` (plazo 7 d al docente) · `POST /sessions/{id}/close` · `GET /attendance/sessions-today` | Asistencias (F3) | A admin · D suyo |
| `GET /attendance/sessions-review` · `POST /sessions/{id}/resolve-review` · `POST /sessions/{id}/cancel` · `POST /blocks/{id}/cancel-day` · `PATCH /attendance/{id}/justify` | Ciclo de sesiones y justificación puntual (F3, Bloque 11) | A admin · D suyo |
| `GET /attendance/me` · `GET /attendance/me/dpi` | "Mis asistencias" y DPI del estudiante (F3b) | Solo rol estudiante |
| `GET /dpi/at-risk` · `GET /students/{id}/dpi` | Riesgo DPI (F5/F6) | A admin · D sus cursos |
| `GET/POST/DELETE /holidays` · `POST /holidays/range` · `POST /holidays/national` · `GET/POST/DELETE /justifications` · `GET/PATCH /settings` | Calendario (F3) | A admin · L docente |
| `POST/GET/DELETE /students/{id}/faces` (`consent: true` obligatorio) | Enrolamiento (F4) | A admin · L docente |
| `GET /dashboard/summary` (+`en_riesgo`, `sessions_to_review`) · `/dashboard/live` (SSE) · `GET /stats/hourly` · `GET /stats/distribution` | Dashboard (F5) | A+D (ambos ya filtrados por grupo si es docente) |
| `GET /reports/attendance.xlsx|pdf` · `GET /reports/group-matrix.xlsx` · `GET /reports/dpi-risk.xlsx` · `POST /courses/import-pdf(+/confirm)` · `GET /audit-log` (+`actor_role`) | Reportes/Importación/Bitácora (F6) | A admin (reportes: D suyo) |
| `GET /devices/{id}` | Detalle de cámara con `rtsp_url` COMPLETA (R14: el listado la enmascara; un PATCH reenviando `***` se ignora) | A admin |

`A`=admin escribe, `D`=docente en sus grupos, `L`=solo lectura. El backend YA aplica todo esto;
la UI solo oculta botones con `@if (auth.isAdmin())`.

## 6. Inconsistencias y avisos detectados al revisar el backend (sin acción urgente)

1. **~~`GET /attendance/sessions-today` NO existe~~ → RESUELTO** (Bloque 6b del
   PLAN-BACKEND; el frontend ya lo consume). **Bloque 11 (2026-10-11):** además el backend
   añadió el ciclo completo de sesiones (apertura por scheduler, `needs_review`,
   cancelación), justificaciones con efecto, DPI con aviso único por nivel y reportes por
   grupo — todo documentado arriba en F2/F3/F4/F5/F6 y en PLAN-BACKEND §3 (Bloque 11).
2. **`app.frontend()` no está implementado** en `main.py` (el plan del backend lo menciona
   para el Bloque 10) → F8 lo implementa junto con la config de producción.
3. **~~Rate limit de login SOLO en el cliente~~ → RESUELTO**: el backend ya limita
   (Bloque 6b: 5 fallos IP/min → 429, login correcto limpia la ventana; con tests).
4. **`GET /devices/status` es PÚBLICO** (sin token): pensado para el panel RF-35 en un solo
   origen. Exponer estados en línea de equipos sin credencial es discutible en producción
   real; opción futura: exigir JWT (1 línea en el endpoint).
5. **~~El badge "Enrolado" en `/students` requeriría N llamadas~~ → RESUELTO**: el backend ya
   soporta `GET /students?with_face=1` (UNA query extra por página, no N por alumno) y el
   frontend ya lo usa para el badge Enrolado/Sin rostro.
6. **Las vistas SQL (`v_today_attendance`) usan `CURRENT_DATE` del servidor**: asume la zona
   horaria de Perú en la PC servidor (la del dev ya lo está). No tocar.
7. **`PersonOut` no expone `photo_url`**: la foto de portada se ve solo en `/faces`; suficiente.

## 7. Fuera de alcance (coherente con PLAN-BACKEND §7)
- Sin PWA/SSR/i18n; sin NgRx/NGXS (signals + services); sin tests e2e Cypress (los smokes
  son manuales por bloque; si sobra tiempo: 2-3 specs de `ng test` para guards y auth).
- El estudiante NO entra al PANEL ADMIN (el guard seguirá bloqueando `/admin`); su vista
  propia "Mis asistencias" (`GET /attendance/me`) se construye en F3b (ver §4). Las
  notificaciones por correo RF-24 se mantienen.
