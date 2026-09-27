# REQUERIMIENTOS FUNCIONALES - FAREAS

> **Sistema de Control de Asistencia con Reconocimiento Facial**
> Facultad de Informática - Universidad Nacional Micaela Bastidas de Apurímac (UNAMBA)
> Abancay, Apurímac, Perú
> Stack: Angular 21 · FastAPI · PostgreSQL 17 (`REAL[512]` + NumPy) · ONNX Runtime CPU (buffalo_l) · Cloudflare (R2 / Tunnel) · ESP32

---

## Índice

- [1. Alcance y dominio](#1-alcance-y-dominio)
- [2. Tabla 1: Especificación Técnica del Hardware Validado (EPIIS-UNAMBA 2026)](#tabla-1)
- [3. Tabla 2: Definición Estricta de Casos de Negocio Especiales](#tabla-2)
- [4. Tabla 3: Módulo de Administración e Infraestructura (Angular)](#tabla-3)
- [5. Tabla 4: Módulo del Estudiante y Docente (Angular)](#tabla-4)
- [6. Tabla 5: Módulo de Procesamiento de IA (Python + FastAPI)](#tabla-5)
- [7. Tabla 6: Lógica de Negocio y Alertas](#tabla-6)
- [8. Tabla 7: Dispositivo Periférico IoT en Puerta (ESP32 Firmware)](#tabla-7)
- [9. Tabla 8: Estados, Alertas y Colores del Anillo LED](#tabla-8)
- [10. Ejemplo del horario de clases de un alumno](#horario)
- [11. Trazabilidad de cambios respecto a la versión anterior](#cambios)

---

<a id="1-alcance-y-dominio"></a>
## 1. Alcance y dominio

El sistema registra la asistencia de los estudiantes a clases de manera automática mediante reconocimiento facial en la puerta del aula, sin intervención del docente. Opera en la Facultad de Informática de la UNAMBA, en un entorno **universitario público peruano**: franja de clases de **07:00 a 20:00 h**, infraestructura de red de campus, correo institucional `@unamba.edu.pe` y contexto legal de datos biométricos (Ley N.º 29733 - Protección de Datos Personales del Perú; los vectores faciales son datos biométricos y, como tales, sensibles).

**Acrónimos y términos:**

| Término | Definición |
|---|---|
| Grupo | División paralela de un curso (A, B, C…) con docente, aula y horario propios. |
| Bloque académico | Par de horas pedagógicas de 2 h (ej. 07:00–09:00). Un curso-grupo se dicta en uno o más bloques por semana. |
| Sesión | Ocurrencia concreta de un bloque académico en un día lectivo. Toda marca de asistencia pertenece a una sesión. |
| Día lectivo | Día del semestre con clases programadas que no es feriado ni día no laborable (RF-09). |
| Marca | Primer registro facial positivo de un estudiante en una sesión. |
| Cooldown | Ventana anti-spam que ignora detecciones repetidas dentro de la misma sesión. |
| DPI | Inhabilitación por Deficiencia Personal Injustificada. |

---

<a id="tabla-1"></a>
## Tabla 1: Especificación Técnica del Hardware Validado (EPIIS-UNAMBA 2026)

| Componente | Modelo Seleccionado | Características Críticas para la Tesis | Función Exacta en el Sistema |
|---|---|---|---|
| Cámara IP Inteligente | Hikvision DS-2CD2347G3-LIS2UY/S(L)(RB) | 4 MP (2688x1520), Procesador HikAI-ISP, Smart Hybrid Light, WDR Adaptativo, Lente fija (2.8mm o 4mm), NEMA 4X. | Captura el flujo de video en el umbral de la puerta. El chip HikAI-ISP limpia el ruido de la imagen antes de enviarla por RTSP, optimizando la precisión de detección. Alimentada y conectada por un único cable Ethernet vía PoE+. |
| Cerebro Periférico IoT | NodeMCU ESP32 WROOM-32 (38 Pines - USB Tipo C) | SoC Dual Core, Conectividad Wi-Fi 802.11 b/g/n, Bluetooth 4.2 BLE, Alimentación 5V vía Tipo C, Tolerancia Lógica 3.3V. | Actúa como nodo receptor en la puerta del aula. Escucha eventos del backend vía Wi-Fi (WebSocket TLS) y controla secuencialmente los indicadores físicos. Reporta latido (heartbeat) cada 30 s. |
| Indicador Visual | Anillo LED RGB NeoPixel (WS2812B) 5050 - 16 Bit | 16 LEDs direccionables individualmente, Controlador WS2812B integrado, Comunicación por un solo hilo a 5V. | Proporciona retroalimentación lumínica al estudiante en tiempo real según el estado de su marca (Verde, Amarillo, Rojo, Azul - ver Tabla 8). |
| Indicador Acústico | Buzzer Activo de 5V | Transductor piezoeléctrico continuo, consumo menor a 30mA, activación por flanco alto directo desde el GPIO. | Genera alertas sonoras de baja intensidad (beeps) sincronizadas con el anillo LED para entornos áulicos silenciosos. |
| Switch PoE+ | TP-Link LS108GP Gigabit | 8 Puertos RJ45 10/100/1000 Mbps, Soporte PoE+ (802.3at/af), Presupuesto Total 62W, Modo Extendido. | Energiza la cámara Hikvision y transporta el video usando un único cable Ethernet Categoría 6, garantizando cero retrasos. También interconecta el servidor backend o el puente Wi-Fi del ESP32 dentro de la red del aula. |
| Router Wi-Fi del Aula *(añadido)* | AP/Router Wi-Fi 802.11 b/g/n (2.4 GHz) | Red dedicada por aula, DHCP estático por MAC, SSID oculto, aislamiento de clientes (client isolation). | Red que une el ESP32 con el switch/servidor. El backend conoce la identidad del aula por el nodo que se conecta, no por su dirección IP dinámica. |

---

<a id="tabla-2"></a>
## Tabla 2: Definición Estricta de Casos de Negocio Especiales

| Caso Especial | Enfoque de Solución Tecnológica (Año 2026) | Flujo Lógico y Almacenamiento |
|---|---|---|
| Optimización Vectorial | Tratamiento nativo de datos biométricos dentro del motor relacional. | FastAPI extrae los vectores faciales (embeddings ArcFace de 512-d) y los almacena en una columna `REAL[512]` de PostgreSQL; la búsqueda por similitud de coseno se ejecuta en Python/NumPy (~0.2 ms medidos contra 5000 alumnos - ver Tabla 9). Las fotos base se guardan inmutables en Cloudflare R2 (bucket privado, URLs firmadas) en producción, o en `storage/` local en desarrollo; PostgreSQL solo persiste la clave del objeto. |
| Manejo de Secciones y Grupos Paralelos | Estructura relacional jerárquica y validación de permisos espaciales. | La matrícula vincula al alumno a un Grupo Específico (A, B o C) de un curso. Si la IA detecta a un alumno intentando ingresar a un grupo/sección en la que no está matriculado, el sistema rechaza el registro (LED Rojo) y lo cataloga como "Intento de acceso no autorizado a otra sección". |
| Lógica de Marca Única (Anti-Spam) | Periodo de latencia (Cooldown) por sesión de bloque académico. | El sistema evalúa únicamente la primera detección del alumno dentro de la franja horaria (sesión). Las detecciones subsecuentes en la misma aula durante ese curso son ignoradas para no saturar la base de datos ni el buzzer de la puerta. La sesión solo admite marcas mientras esté abierta (RF-26). |
| Conflictos por Cruces | Resolución espacial biunívoca basada en la localización física del hardware. | Si hay cruce de horarios, se compara el ID de la cámara. El sistema asigna la asistencia exclusivamente al grupo/curso dictado en el aula donde el estudiante fue detectado físicamente. |
| Validación Cruzada de Sesión *(añadido)* | Doble filtro temporal-espacial antes de emitir veredicto. | El backend resuelve la sesión activa con la tripleta (cámara → aula, día, hora) y solo entonces valida matrícula, cooldown y estado. Ninguna marca se procesa fuera de una sesión abierta: se responde en la puerta "Sin clase programada" (LED azul, Tabla 8) sin escribir en la base de datos. |

---

<a id="tabla-3"></a>
## Tabla 3: Requerimientos Funcionales - Módulo de Administración e Infraestructura (Angular)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-01 | Gestión de Roles (RBAC) | El sistema debe autenticar y segmentar las interfaces según tres roles: **Administrador, Docente y Estudiante**. Las rutas del frontend y los permisos del backend (JWT con rol) se validan en ambos extremos; un docente solo accede a sus grupos, un estudiante solo a su propio récord. |
| RF-02 | Registro de Docentes | El sistema debe permitir al administrador registrar profesores capturando: DNI, Nombres, Apellidos, Correo Institucional y Número de WhatsApp. |
| RF-03 | Registro de Matrícula Estudiantil | El sistema debe permitir registrar al alumno capturando: DNI, Código de Matrícula, Nombres, Apellidos, Semestre Académico (Ciclo), Correo Institucional y WhatsApp del estudiante. |
| RF-04 | Enrolamiento Biométrico Facial | El sistema debe permitir la carga de 3 a 5 capturas fotográficas frontales del estudiante para generar el vector base inicial. El backend calcula un embedding por foto (ArcFace ONNX), valida la consistencia entre capturas (coseno intra-alumno) y guarda el promedio como vector vigente del alumno en la columna `REAL[512]` (Tabla 9); las fotos se almacenan en Cloudflare R2 (producción) o `storage/` local (desarrollo). |
| RF-05 | Catálogo de Infraestructura | El sistema debe registrar las aulas mapeando la IP de la cámara Hikvision y la dirección IP/MAC del módulo ESP32 asociado. Cada aula registra exactamente una cámara y un nodo ESP32; el backend identifica el aula por la identidad del nodo conectado (RF-33). |
| RF-06 | Gestión de Carga Académica | El administrador debe configurar el horario general: crear cursos, dividirlos en grupos (A, B, C ...), asignarles aula, horario (bloques de 2 h entre 07:00 y 20:00) y docente responsable. El sistema debe rechazar asignaciones que choquen en la misma aula o docente en el mismo bloque. |
| RF-07 | Extracción de Horarios por OCR | El sistema debe procesar PDFs de matrículas, extrayendo automáticamente: Curso, Grupo/Sección, Día y Hora. El resultado se presenta en una pantalla de confirmación para revisión del administrador antes de persistir la matrícula; los registros ambiguos se marcan para corrección manual. |
| RF-08 | Despacho de Credenciales Iniciales | Al registrar a un nuevo Docente o Estudiante, el sistema generará una clave temporal aleatoria y la enviará automáticamente al correo institucional del usuario (`@unamba.edu.pe`) para su primer acceso. |
| RF-09 | Gestión de Feriados y Paros | El administrador debe poder registrar fechas como "Días No Laborables" para evitar que el sistema genere faltas masivas automatizadas. El calendario aplica al cierre automático de sesiones (RF-26): en días no laborables no se abren sesiones ni se computan faltas. |
| RF-10 | Registro de faltas justificadas | El administrador debe poder ingresar "Descansos Médicos u otro tipo de falta justificada" para un alumno, congelando la generación de faltas durante ese rango de fechas. Las faltas ya generadas dentro del rango se reclasifican como justificadas y no cuentan para el DPI (RF-24). |
| RF-34 | Configuración Global del Semestre *(nuevo)* | El administrador debe poder definir los parámetros académicos que gobiernan la lógica: fecha de inicio y fin del semestre, duración del bloque académico (por defecto 2 h), minutos de tolerancia (RF-23), umbral de DPI (RF-24) y los feriados del ciclo. Un cambio de parámetros aplica a las sesiones siguientes, nunca retroactivamente. |
| RF-35 | Monitoreo de Dispositivos *(nuevo)* | El administrador debe visualizar el estado de conexión de cada nodo ESP32 y de cada cámara (en línea / fuera de línea, último latido, última cámara vista) para detectar aulas con equipos caídos antes de que la falta de monitoreo genere registros perdidos (RF-33). |

---

<a id="tabla-4"></a>
## Tabla 4: Requerimientos Funcionales - Módulo del Estudiante y Docente (Angular)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-11 | Autenticación y Cambio Obligatorio de Clave | El usuario debe iniciar sesión con sus credenciales cifradas (JWT). Si ingresa con una clave temporal, el sistema bloqueará el acceso hasta que configure una nueva contraseña privada. |
| RF-12 | Recuperación de Acceso vía OTP | El sistema despachará un código temporal de 6 dígitos al correo institucional del usuario para validar el proceso de restauración de contraseña en caso de olvido. |
| RF-13 | Dashboard de Récord Estudiantil | El estudiante visualizará un consolidado de asistencias filtrado por cursos, grupos y fechas, incluyendo su porcentaje acumulado por curso frente al límite de inhabilitación (RF-24). El estudiante consulta su propio récord; no existe visibilidad cruzada entre estudiantes. |
| RF-14 | Panel Dinámico Docente | Al iniciar sesión, el docente visualizará la nómina de alumnos de su sección específica, actualizándose en tiempo real conforme la IA registra ingresos. |
| RF-15 | Panel de Rectificación Docente | El docente tendrá el privilegio exclusivo de modificar un estado de asistencia en su lista actual bajo justificación válida presencial. Cada rectificación queda registrada con usuario, motivo y fecha/hora (RF-32), sin destruir el valor original. |
| RF-16 | Exportación de Reportes | El docente podrá generar archivos Excel y PDF con las estadísticas de asistencia de su grupo para entregar a dirección o SUNEDU. Los documentos llevan fecha de emisión, curso, grupo, docente y rango de fechas del reporte. |

---

<a id="tabla-5"></a>
## Tabla 5: Requerimientos Funcionales - Módulo de Procesamiento de IA (Python + FastAPI)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-17 | Ingesta y Decodificación RTSP | El backend se conectará al stream de la cámara Hikvision, aislando los fotogramas clave. La frecuencia de análisis es configurable por aula (por defecto 2 fps) para equilibrar carga de CPU y latencia de detección. |
| RF-18 | Aislamiento Facial Adaptativo | Se emplearán modelos (YOLOv8-face / YOLOv10) para detectar rostros en el umbral, incluso con flujo denso. |
| RF-19 | Extracción e Identificación | El sistema vectorizará el rostro (ArcFace ONNX, embedding de 512 dimensiones, pesos preentrenados buffalo_l - Tabla 9) y realizará la búsqueda por distancia de coseno contra los embeddings vigentes en PostgreSQL (NumPy; la interfaz queda encapsulada para migrar a pgvector si la escala lo exigiera). |
| RF-20 | Filtrado por Umbral de Similitud | El sistema rechazará detecciones con coincidencia inferior al 75%, catalogándolas como "Sujeto No Identificado". Las detecciones entre el 75% y el umbral superior definido en RF-31 se marcan para revisión en el panel de auditoría sin emitir veredicto en la puerta. |

---

<a id="tabla-6"></a>
## Tabla 6: Requerimientos Funcionales - Lógica de Negocio y Alertas

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-21 | Auditoría de Ingreso (Timestamp) | El sistema capturará la hora exacta de la primera identificación positiva cruzando la puerta. Los timestamps se registran en hora local de Apurímac (America/Lima, UTC-5) y se almacenan en UTC. |
| RF-22 | Validación Estricta de Matrícula | El sistema cruzará el ID del alumno para confirmar que pertenece al grupo/sección que recibe clases en esa aula. |
| RF-23 | Clasificación de Asistencia | Si el alumno está en el grupo correcto, el sistema evalúa el registro respecto al inicio del bloque: **Asistió** (≤ 10 min), **Tardanza** (> 10 min). El estudiante matriculado que no genere ninguna marca dentro de la sesión abierta se clasifica **Falta** únicamente por el cierre automático (RF-26). Los tres estados son mutuamente excluyentes y completos. |
| RF-24 | Alerta de Inhabilitación (DPI) | El sistema calculará el porcentaje acumulado de faltas. El reglamento es **1/3 (33.33%)** de asistencias del curso; el umbral preventivo del **30%** de faltas acumuladas dispara una alerta crítica a Dirección y Estudiante (correo institucional) antes de alcanzar la inhabilitación. El porcentaje se recalcula con cada cierre de sesión (RF-26) y es visible para el estudiante en su dashboard (RF-13). |
| RF-25 | Orquestación de Feedback | El backend enviará asíncronamente un payload al ESP32 ordenando el color: Verde/Amarillo (Grupo correcto) o Rojo (Grupo incorrecto o sujeto no identificado), mediante protocolo WebSocket. El payload incluye el estado, el mensaje corto para la puerta y el tiempo de visualización. |
| RF-26 | Cierre Automático de Sesión *(nuevo)* | Al finalizar cada bloque académico de un día lectivo, el backend cerrará la sesión correspondiente: los estudiantes matriculados sin marca se clasifican **Falta**, y la sesión pasa a estado `cerrado` inmutable. El proceso corre como tarea programada tolerante a reinicios; si el servidor estuvo caído, el cierre se ejecuta de forma diferida al recuperar el servicio, registrando la hora real de ejecución. Las sesiones de días no laborables (RF-09) nunca se abren. |
| RF-32 | Trazabilidad y Auditoría *(nuevo)* | Toda acción sensible - rectificación docente (RF-15), justificación (RF-10), cambio de estado, reenvío de credenciales - se registra en una bitácora de auditoría con actor, fecha/hora, entidad afectada, valor anterior y nuevo. La bitácora es de solo lectura para el administrador y soporta la defensa de la tesis frente a los comités de ética. |

---

<a id="tabla-7"></a>
## Tabla 7: Requerimientos Funcionales - Dispositivo Periférico IoT en Puerta (ESP32 Firmware)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-27 | Estado Cíclico de Reposo | El firmware mantendrá el anillo LED mostrando una animación azul de baja intensidad en espera. |
| RF-28 | Confirmación Visual | El ESP32 conmutará el anillo LED: Verde (Asistió), Amarillo (Tardanza), Rojo (Denegado), Azul (sin clase programada / en espera - ver Tabla 8). |
| RF-29 | Disparo Acústico Sincronizado | El ESP32 excitará el buzzer: 1 Beep corto (Éxito), 2 Beeps (Tardanza), Tono sostenido (Error). |
| RF-33 | Identidad y Latido del Nodo *(nuevo)* | El firmware presentará credenciales de dispositivo al conectar el WebSocket y reportará un latido (heartbeat) cada 30 s con su identificador y RSSI. Si el backend no recibe latidos durante 90 s, marcará el nodo como fuera de línea (RF-35); si el nodo pierde la conexión, ejecutará reconexión con backoff exponencial y animación de error persistente en el anillo. |

---

<a id="tabla-8"></a>
## Tabla 8: Estados, Alertas y Colores del Anillo LED *(nueva)*

Semáforo unificado entre backend, frontend y firmware. Un solo catálogo evita que cada capa invente colores para el mismo concepto.

| Estado | Color LED | Buzzer | Mensaje en la puerta | Registro en base de datos |
|---|---|---|---|---|
| Asistió | Verde | 1 beep corto | "Registro correcto" | Sí - sesión abierta |
| Tardanza | Amarillo | 2 beeps cortos | "Registro con tardanza" | Sí - sesión abierta |
| Denegado - no matriculado | Rojo | Tono sostenido | "No está matriculado en esta sección" | Sí - log de intento no autorizado (Tabla 2) |
| Denegado - sujeto no identificado | Rojo | Tono sostenido | "Sujeto no identificado" | Sí - log de detección bajo umbral (RF-20) |
| Sin clase programada | Azul | Silencio | "Sin clase en este horario" | No |
| Fuera de línea | Parpadeo rojo lento | Silencio | - | Log del evento en el backend (RF-35) |

---

<a id="tabla-9"></a>
## Tabla 9: Decisiones Técnicas Definitivas *(nueva)*

Decisiones de arquitectura acordadas para el desarrollo 2026, priorizando un alcance académico profesional sin sobre-ingeniería empresarial.

| Decisión | Elección | Justificación |
|---|---|---|
| Almacenamiento y búsqueda vectorial | Columna `REAL[512]` + similitud coseno en Python/NumPy (sin pgvector) | 0.23 ms medidos contra 5000 alumnos; compatible con el instalador oficial de PostgreSQL para Windows, sin extensiones adicionales. La búsqueda vive encapsulada en `recognizer.search()`, migrable a pgvector si la escala creciera. |
| Modelos de visión | Pesos preentrenados **buffalo_l** en ONNX (SCRFD `det_10g.onnx` + ArcFace `w600k_r50.onnx`) sobre onnxruntime en CPU | Satisfacen RF-18/RF-19 (detector tipo YOLO-face + ArcFace 512-d) **sin entrenar nada**: el "aprendizaje" del sistema es el enrolamiento (RF-04). Carga en CPU: 0.1–0.3 s. |
| Contenedores | **Sin Docker**: PostgreSQL (instalador oficial Windows), venv de Python, paquetes vía pip | OpenCV y ONNX Runtime se instalan nativos sin compilar; Docker solo se reconsideraría si se migrara a pgvector. |
| Colas, caché y tareas programadas | **Sin Redis ni Celery**: motor de asistencia en el proceso FastAPI, APScheduler para el cierre automático (RF-26), `asyncio.Queue` en memoria para frames | Escala de una facultad (cientos de alumnos, un proceso); infraestructura empresarial innecesaria y difícil de defender en la demo. |
| Versionado del esquema de BD | Scripts SQL manuales numerados (`db/001_schema.sql`, `002_seed.sql`, `003_…`) ejecutados a mano en pgAdmin/psql; **sin Alembic** | Cada cambio es un archivo auditable e idempotente, ideal para la trazabilidad de la tesis; el desarrollador controla exactamente qué se ejecuta. |
| ORM | SQLModel (async, asyncpg) que **mapea** el esquema; jamás `create_all()` | La base manda: los modelos se adaptan al SQL aprobado, no al revés. |
| Entrega del frontend en producción | Servido por el propio FastAPI (`app.frontend()`) y expuesto vía Cloudflare Tunnel | Un solo origen (sin CORS), sin servidores ni workers adicionales. |

---

<a id="horario"></a>
## Ejemplo del horario de clases de un alumno

Aclara que las clases o el horario de clases en la universidad son de 7.00 AM a 20:00 PM, este solo es un ejemplo de como son los horarios del alumno, depende de como le va en el año para que sus horario de organize/desorganize.

| Horario | Lunes | Martes | Miércoles | Jueves | Viernes |
|---|---|---|---|---|---|
| 07:00 - 09:00 | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) | ISA901 Computación Gráfica (LAB 401)<br>MAMANI VILCA, Eddy (Dr.) | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) | ISA901 Computación Gráfica (LAB 401)<br>MAMANI VILCA, Eddy (Dr.) | ISA904 Programación Paralela (LAB 304) |
| 09:00 - 11:00 | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) |
| 11:00 - 13:00 | ISA906 Interacción Humano Computador (LAB 304)<br>ROJAS ENRIQUEZ, Hermenegildo (Dr.) | Tutoría | ISA906 Interacción Humano Computador (LAB 304)<br>ROJAS ENRIQUEZ, Hermenegildo (Dr.) | ISA904 Programación Paralela (LAB 304) | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) |
| 14:00 - 16:00 | - | ISA904 Programación Paralela (LAB 306) | - | - | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) |

> **Nota (regla de negocio derivada):** el ejemplo muestra bloques de 2 horas consecutivos por curso, consistente con la definición de bloque académico de la sección 1. "Tutoría" es una actividad sin aula asignada y por tanto sin registro facial: no genera sesión ni asistencia.

---

<a id="cambios"></a>
## 11. Trazabilidad de cambios respecto a la versión anterior

| Cambio | Justificación |
|---|---|
| Renumeración continua RF-01…RF-33 sin saltos (RF-26 ya no se omite). | La numeración es la llave primaria del documento para la tesis; un salto sugiere requisitos eliminados y complica la trazabilidad. Los RF nuevos se añaden al final de cada tabla (RF-34, RF-35) y la lógica de negocio (RF-26, RF-32) y firmware (RF-33) conservan continuidad. |
| "gmail" → correo institucional (`@unamba.edu.pe`) en RF-08 y RF-12. | La universidad entrega correos institucionales; depender de Gmail personal impide validar identidad, incumple políticas de datos y no escala a todo el plantel. |
| RF-23: "Falta" definida por cierre automático (RF-26); estados completos y excluyentes. | Antes "Falta" no tenía regla de origen: un estudiante ausente solo puede clasificarse cuando la sesión termina, no en tiempo real. |
| RF-24: reglamento 1/3 (33.33%) como límite real y 30% como umbral preventivo de alerta. | La descripción original era contradictoria ("alcanzar el límite del 30%"). El reglamento UNAMBA inhabilita con 1/3 de faltas. |
| Añadidos RF-26 (cierre automático), RF-32 (auditoría), RF-33 (heartbeat), RF-34 (parámetros de semestre), RF-35 (monitoreo). | Sin cierre automático no existen las faltas; sin auditoría no hay trazabilidad de rectificaciones; sin heartbeat el sistema no distingue "aula vacía" de "equipo caído". Todos derivan directamente de los RF existentes. |
| Tabla 8 nueva: catálogo único de estados/colores/mensajes/logs. | Backend, frontend y firmware deben responder con el mismo semáforo; antes cada tabla definía colores por separado y quedaba ambiguo el caso "sin clase". |
| Tabla 2: añadida la validación cruzada de sesión (tripleta cámara-aula/día/hora antes de emitir veredicto). | Formaliza el orden de evaluación que los RF-22/23/25 asumían implícito. |
| Añadido Router Wi-Fi del aula a la Tabla 1. | El ESP32 se conecta por Wi-Fi pero el presupuesto hardware solo listaba el switch PoE cableado: faltaba el componente que hace posible el requisito. |
| Horario de ejemplo regrouped en bloques de 2 h, nota sobre Tutoría. | Alinea el ejemplo con la definición de bloque académico y aclara por qué Tutoría no genera asistencia. |
| Sección 1 (alcance y dominio) y glosario añadidos; índice navegable. | Define bloque, sesión, marca, cooldown y DPI que las tablas usan sin definirlas. |
| pgvector reemplazado por `REAL[512]` + coseno en NumPy (Tabla 2, RF-04, RF-19, Tabla 9 nueva). | Benchmark propio: 0.23 ms contra 5000 alumnos; elimina la dependencia de una extensión no incluida en el instalador oficial de PostgreSQL para Windows. |
| "Se emplearán modelos (YOLOv8-face / YOLOv10)" (RF-18) materializado en pesos SCRFD+ArcFace ONNX preentrenados (Tabla 9). | Cumple el espíritu del RF (detección facial robusta + ArcFace) sin entrenamiento: inviable académicamente y innecesario para el alcance. |
