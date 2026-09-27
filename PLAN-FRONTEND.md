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
| AuthService | signals `currentUser/isAuthenticated/isAdmin/isDocente/mustChangePassword`, rate-limit cliente, sin refresh tokens (coherente backend) |
| Interceptor 401 | `core/interceptors/auth.ts` → limpia sesión y manda a `/login?reason=session_expired` |
| Layout admin | `layouts/admin` con Sidebar + Header funcionales (menú PLANO: Dashboard, Asistencias) |
| Dashboard mock | 4 tarjetas, activity-feed con `setInterval`, hourly-chart, distribution-chart, student-list (todos con MOCK data) |
| Asistencia mock | `features/attendance` con tabla estática |
| Build OK | `ng build --configuration development` pasa; `dist/fareas` generado |

**Stack fijo:** Angular 21 (standalone + signals + OnPush), PrimeNG 20, Tailwind 4,
Chart.js 4, material-symbols/akar-icons ya en uso.

## 1. Decisiones definitivas (respondidas por el usuario)

1. **El rol ESTUDIANTE no entra al panel** (por ahora): el guard de `/admin` solo
   deja pasar `admin` y `docente`. El estudiante recibe sus alertas por correo
   (RF-24). Si en el futuro se quiere "Mis asistencias", se añade `GET /attendance/me`.
2. **Hardware al final (F7)**: cámara Hikvision + ESP32 se conectan cuando el
   frontend puede MONITOREARLOS (RF-35) — así cada paso se verifica desde la UI.
3. **Sidebar agrupado con submenús** (secciones colapsables), con visibilidad por rol.
4. **Backend mínimo extra aprobado**: `GET /attendance/sessions-today`
   (sesiones abiertas de hoy con session_id/curso/grupo/aula/estado) para el modal
   de marca manual RF-21 — se implementa al inicio de F3 (~30 líneas, patrón ya existente).

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
  sus grupos (`GET /courses/{id}/groups`), crear grupo (docente+aula: selects de `/teachers` y
  `/rooms`) → detalle de grupo con BLOQUES horarios (grid semanal LUN-DOM, crear/patch/delete con
  detección de choque RF-06 mostrando el 409 del backend como toast).
- [ ] **Matrículas** `/enrollments`: selector curso→grupo (`GET /courses` + `GET /courses/{id}/groups`)
  + listar/alta/quitar alumnos (`GET/POST/DELETE /groups/{id}/students`, autocomplete de estudiantes).
- **Entregable:** admin puede montar la malla completa desde la UI sin pgAdmin; docente la ve.

### F3 - Asistencia y calendario (1 día) - RF-09, RF-10, RF-15, RF-21, RF-26, RF-34
- [ ] **Backend (~30 min, aprobado):** `GET /attendance/sessions-today` →
  `[{session_id, course_code, course_name, group_code, room_code, weekday, start_time, end_time,
  status, total_marcas}]` (sesiones de hoy abiertas+cerradas del docente o todas para admin).
- [ ] **Asistencias** `/attendance`: tabla en vivo de HOY desde `GET /attendance/today` con filtros
  curso/aula/estado (refresh manual + botón); **modal marca manual RF-21**: seleccionar sesión
  (de `sessions-today`) → estudiante (solo matriculados del grupo) → estado → `POST /sessions/{id}/manual-mark`;
  **rectificar RF-15**: acción de fila con dialog motivo → `PATCH /attendance/{id}/rectify`;
  botón "Cerrar sesión" (admin) → `POST /sessions/{id}/close` con resumen de faltas.
- [ ] **Feriados** `/calendar/holidays`: lista + alta/baja — `GET/POST /holidays`, `DELETE /holidays/{id}`.
- [ ] **Justificaciones** `/calendar/justifications`: lista filtrable por alumno + alta
  (rango fechas, motivo, curso opcional, documento URL) — `GET/POST /justifications`, `DELETE /justifications/{id}`.
- [ ] **Parámetros** `/calendar/settings`: formulario semestre/bloque/tolerancia/umbrales —
  `GET/PATCH /settings` (aviso: "aplica a sesiones siguientes, nunca retroactivo" RF-34).
- **Entregable:** el flujo completo de un día lectivo se opera 100% desde la UI.

### F4 - Enrolamiento facial (½-1 día) - RF-04, RF-20
- [ ] Página `/faces`: buscar estudiante → `GET /students/{id}/faces` muestra estado actual
  (enrolado sí/no, foto, fecha); flujo de captura: **webcam** (`navigator.mediaDevices.getUserMedia`,
  botón capturar ×N) O **subir archivos** (input multiple); client-side: comprimir a JPEG ~640px,
  convertir a base64 → `POST /students/{id}/faces` con `{photos: [...]}` (3-5).
- [ ] Manejo de errores del validador facial: 1 rostro por foto, consistencia ≥0.55,
  duplicado → mensajes claros del backend en toasts.
- [ ] En `/students`: badge de enrolamiento + acción directa "Enrolar rostro".
- **Entregable:** enrolar a un alumno desde la webcam y verlo identificado en el video demo
  (`scripts/simulate_camera.py`) sin tocar la BD a mano.

### F5 - Dashboard en vivo (1 día) - RF-13, RF-35, PLAN §5
- [ ] `DashboardApi`: `GET /dashboard/summary` → las 4 tarjetas reales (asistencias/tardanzas/
  ausencias con %, cámaras activas, alertas DPI) con auto-refresh 30 s.
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
- [ ] **Importar horario** `/imports` (RF-07, 2 pasos): subir PDF → tabla editable de la
  previsualización (`POST /courses/import-pdf`) con filas ambiguas resaltadas (chip "Ambiguo"
  + `nota`), select de docente y aula → confirmar → `POST /courses/import-pdf/confirm`
  → resumen de creados (cursos/grupos/bloques) y manejo del 409 de choque (todo-o-nada).
- [ ] **Bitácora** `/audit` (admin): tabla paginada `GET /audit-log` con filtros
  action/entity/entity_id/actor/since (backend ya los soporta) + visor de old/new_value (JSON).
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
| Buzzer + | **GPIO 12** | si el buzzer es de 5 V "duro": transistor 2N2222 (base 1 kΩ a GPIO12) |
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
#define BUZZ_PIN 12
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
  · azul = animación de reposo (el sketch hace fade simple: ampliable en F7).

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
| `POST /auth/login` · `GET /auth/me` · `POST /auth/change-password` · `/auth/recover/*` | Login/recuperación (YA) | todos |
| `GET/POST /rooms` · `PATCH /rooms/{id}` | Aulas (F2) | A admin · L docente |
| `GET/POST /devices` · `PATCH /devices/{id}` · `GET /devices/status` | Dispositivos + Monitoreo RF-35 (F2/F5) | A admin · status público |
| `GET/POST /teachers` · `GET/POST /students` · `GET/PATCH /accounts/{id}` · `POST /accounts/{id}/send-temp-password` | Catálogo de personas (F2) | A admin · L docente |
| `GET/POST /courses` · `GET/POST /courses/{id}/groups` · `GET/POST /groups/{id}/blocks` · `PATCH/DELETE /blocks/{id}` · `DELETE /groups/{id}` | Cursos y grupos (F2) | A admin · L docente |
| `GET/POST/DELETE /groups/{id}/students` | Matrículas (F2) | A admin · L docente |
| `GET /attendance/today` · `POST /sessions/{id}/manual-mark` · `PATCH /attendance/{id}/rectify` · `POST /sessions/{id}/close` · `GET /attendance/sessions-today` (nuevo) | Asistencias (F3) | A admin · D suyo |
| `GET/POST/DELETE /holidays` · `GET/POST/DELETE /justifications` · `GET/PATCH /settings` | Calendario (F3) | A admin · L docente |
| `POST/GET /students/{id}/faces` | Enrolamiento (F4) | A admin · L docente |
| `GET /dashboard/summary` · `/dashboard/live` (SSE) · `GET /stats/hourly` · `GET /stats/distribution` | Dashboard (F5) | A+D (SSE por query) |
| `GET /reports/attendance.xlsx|pdf` · `POST /courses/import-pdf(+/confirm)` · `GET /audit-log` | Reportes/Importación/Bitácora (F6) | A admin (reportes: D suyo) |

`A`=admin escribe, `D`=docente en sus grupos, `L`=solo lectura. El backend YA aplica todo esto;
la UI solo oculta botones con `@if (auth.isAdmin())`.

## 6. Inconsistencias y avisos detectados al revisar el backend (sin acción urgente)

1. **`GET /attendance/sessions-today` NO existe** → aprobado añadirlo (inicio de F3). Sin él,
   el modal de marca manual no sabe qué sesión abierta corresponde a cada aula/curso.
2. **`app.frontend()` no está implementado** en `main.py` (el plan del backend lo menciona
   para el Bloque 10) → F8 lo implementa junto con la config de producción.
3. **Rate limit de login SOLO en el cliente** (`auth-rate-limit.ts`): el endpoint
   `POST /auth/login` del backend no limita intentos. Para la tesis alcanza; si el tribunal
   pregunta por seguridad, añadir un limitador simple en el backend (dict IP→intentos, 5/min).
4. **`GET /devices/status` es PÚBLICO** (sin token): pensado para el panel RF-35 en un solo
   origen. Exponer estados en línea de equipos sin credencial es discutible en producción
   real; opción futura: exigir JWT (1 línea en el endpoint).
5. **El badge "Enrolado" en `/students`** requeriría N llamadas (`GET /students/{id}/faces` por
   alumno). Para el directorio completo: opcional añadir `GET /students?with_face=1` al backend
   (o aceptar N llamadas solo al abrir el enrolamiento individual — plan actual).
6. **Las vistas SQL (`v_today_attendance`) usan `CURRENT_DATE` del servidor**: asume la zona
   horaria de Perú en la PC servidor (la del dev ya lo está). No tocar.
7. **`PersonOut` no expone `photo_url`**: la foto de portada se ve solo en `/faces`; suficiente.

## 7. Fuera de alcance (coherente con PLAN-BACKEND §7)
- Sin PWA/SSR/i18n; sin NgRx/NGXS (signals + services); sin tests e2e Cypress (los smokes
  son manuales por bloque; si sobra tiempo: 2-3 specs de `ng test` para guards y auth).
- El estudiante NO entra al panel (decisión §1); notificaciones por correo RF-24 ya existentes.
