# REQUERIMIENTOS FUNCIONALES

## Tabla 1: Especificación Técnica del Hardware Validado (EPIIS-UNAMBA 2026)

| Componente | Modelo Seleccionado | Características Críticas para la Tesis | Función Exacta en el Sistema |
|---|---|---|---|
| Cámara IP Inteligente | Hikvision DS-2CD2347G3-LIS2UY/S(L)(RB) | 4 MP (2688x1520), Procesador HikAI-ISP, Smart Hybrid Light, WDR Adaptativo, Lente fija (2.8mm o 4mm), NEMA 4X. | Captura el flujo de video en el umbral de la puerta. El chip HikAI-ISP limpia el ruido de la imagen antes de enviarla por RTSP, optimizando la precisión de detección. |
| Cerebro Periférico IoT | NodeMCU ESP32 WROOM-32 (38 Pines - USB Tipo C) | SoC Dual Core, Conectividad Wi-Fi 802.11 b/g/n, Bluetooth 4.2 BLE, Alimentación 5V vía Tipo C, Tolerancia Lógica 3.3V. | Actúa como nodo receptor en la puerta del aula. Escucha eventos del backend vía Wi-Fi y controla secuencialmente los indicadores físicos. |
| Indicador Visual | Anillo LED RGB NeoPixel (WS2812B) 5050 - 16 Bit | 16 LEDs direccionables individualmente, Controlador WS2812B integrado, Comunicación por un solo hilo a 5V. | Proporciona retroalimentación lumínica al estudiante en tiempo real según el estado de su marca (Verde, Amarillo, Rojo, Azul). |
| Indicador Acústico | Buzzer Activo de 5V | Transductor piezoeléctrico continuo, consumo menor a 30mA, activación por flanco alto directo desde el GPIO. | Genera alertas sonoras de baja intensidad (beeps) sincronizadas con el anillo LED para entornos áulicos silenciosos. |
| Switch PoE+ | TP-Link LS108GP Gigabit | 8 Puertos RJ45 10/100/1000 Mbps, Soporte PoE+ (802.3at/af), Presupuesto Total 62W, Modo Extendido. | Energiza la cámara Hikvision y transporta el video usando un único cable Ethernet Categoría 6, garantizando cero retrasos. |

## Tabla 2: Definición Estricta de Casos de Negocio Especiales

| Caso Especial | Enfoque de Solución Tecnológica (Año 2026) | Flujo Lógico y Almacenamiento |
|---|---|---|
| Optimización Vectorial | Tratamiento nativo de datos biométricos dentro del motor relacional. | FastAPI extrae los vectores faciales (embeddings) y los almacena en columnas tipo VECTOR en PostgreSQL. Las fotos base se guardan inmutables en Cloudflare R2. |
| Manejo de Secciones y Grupos Paralelos | Estructura relacional jerárquica y validación de permisos espaciales. | La matrícula vincula al alumno a un Grupo Específico (A, B o C) de un curso. Si la IA detecta a un alumno intentando ingresar a un grupo/sección en la que no está matriculado, el sistema rechaza el registro (LED Rojo) y lo cataloga como "Intento de acceso no autorizado a otra sección". |
| Lógica de Marca Única (Anti-Spam) | Periodo de latencia (Cooldown) por bloque de horario académico. | El sistema evalúa únicamente la primera detección del alumno dentro de la franja horaria. Las detecciones subsecuentes en la misma aula durante ese curso son ignoradas para no saturar la base de datos ni el buzzer de la puerta. |
| Conflictos por Cruces | Resolución espacial biunívoca basada en la localización física del hardware. | Si hay cruce de horarios, se compara el ID de la cámara. El sistema asigna la asistencia exclusivamente al grupo/curso dictado en el aula donde el estudiante fue detectado físicamente. |

## Tabla 3: Requerimientos Funcionales - Módulo de Administración e Infraestructura (Angular)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-01 | Gestión de Roles (RBAC) | El sistema debe autenticar y segmentar las interfaces según tres roles: Administrador, Docente y Estudiante. |
| RF-02 | Registro de Docentes | El sistema debe permitir al administrador registrar profesores capturando: DNI, Nombres, Apellidos, Correo Institucional y Número de WhatsApp. |
| RF-03 | Registro de Matrícula Estudiantil | El sistema debe permitir registrar al alumno capturando: DNI, Código de Matrícula, Nombres, Apellidos, Semestre Académico (Ciclo), Correo Institucional, WhatsApp del estudiante. |
| RF-04 | Enrolamiento Biométrico Facial | El sistema debe permitir la carga de 3 a 5 capturas fotográficas frontales del estudiante para generar el vector base inicial. |
| RF-05 | Catálogo de Infraestructura | El sistema debe registrar las aulas mapeando la IP de la cámara Hikvision y la dirección IP/MAC del módulo ESP32 asociado. |
| RF-06 | Gestión de Carga Académica | El administrador debe configurar el horario general: crear cursos, dividirlos en grupos (A, B, C ...), asignarles aula, horario y docente responsable. |
| RF-07 | Extracción de Horarios por OCR | El sistema debe procesar PDFs de matrículas, extrayendo automáticamente: Curso, Grupo/Sección, Día y Hora. |
| RF-08 | Despacho de Credenciales Iniciales | Al registrar a un nuevo Docente o Estudiante, el sistema generará una clave temporal aleatoria y la enviará automáticamente al gmail del usuario para su primer acceso. |
| RF-09 | Gestión de Feriados y Paros | El administrador debe poder registrar fechas como "Días No Laborables" para evitar que el sistema genere faltas masivas automatizadas. |
| RF-10 | Registro de falta justificadas | El administrador debe poder ingresar "Descansos Médicos u otro tipo de falta justificada" para un alumno, congelando la generación de faltas durante ese rango de fechas. |

## Tabla 4: Requerimientos Funcionales - Módulo del Estudiante y Docente (Angular)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-11 | Autenticación y Cambio Obligatorio de Clave | El usuario debe iniciar sesión con sus credenciales cifradas (JWT). Si ingresa con una clave temporal, el sistema bloqueará el acceso hasta que configure una nueva contraseña privada. |
| RF-12 | Recuperación de Acceso vía OTP | El sistema despachará un código temporal de 6 dígitos al gmail del usuario para validar el proceso de restauración de contraseña en caso de olvido. |
| RF-13 | Dashboard de Récord Estudiantil | El estudiante visualizará un consolidado de asistencias filtrados por cursos, grupos y fechas. |
| RF-14 | Panel Dinámico Docente | Al iniciar sesión, el docente visualizará la nómina de alumnos de su sección específica, actualizándose en tiempo real conforme la IA registra ingresos. |
| RF-15 | Panel de Rectificación Docente | El docente tendrá el privilegio exclusivo de modificar un estado de asistencia en su lista actual bajo justificación válida presencial. |
| RF-16 | Exportación de Reportes | El docente podrá generar archivos Excel y PDF con las estadísticas de asistencia de su grupo para entregar a dirección o SUNEDU. |

## Tabla 5: Requerimientos Funcionales - Módulo de Procesamiento de IA (Python + FastAPI)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-17 | Ingesta y Decodificación RTSP | El backend se conectará al stream de la cámara Hikvision, aislando los fotogramas clave. |
| RF-18 | Aislamiento Facial Adaptativo | Se emplearán modelos (YOLOv8-face / YOLOv10) para detectar rostros en el umbral, incluso con flujo denso. |
| RF-19 | Extracción e Identificación | El sistema vectorizará el rostro (ArcFace) y realizará la búsqueda por distancia de cosenos en PostgreSQL. |
| RF-20 | Filtrado por Umbral de Similitud | El sistema rechazará detecciones con coincidencia inferior al 75%, catalogándolas como "Sujeto No Identificado". |

## Tabla 6: Requerimientos Funcionales - Lógica de Negocio y Alertas

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-21 | Auditoría de Ingreso (Timestamp) | El sistema capturará la hora exacta de la primera identificación positiva cruzando la puerta. |
| RF-22 | Validación Estricta de Matrícula | El sistema cruzará el ID del alumno para confirmar que pertenece al grupo/sección que recibe clases en esa aula. |
| RF-23 | Clasificación de Asistencia | Si el alumno está en el grupo correcto, el sistema evalúa el registro: Asistió (<= 10 min), Tardanza (> 10 min), o Falta. |
| RF-24 | Alerta de Inhabilitación (DPI) | El sistema calculará el porcentaje acumulado de faltas. Al alcanzar el límite preventivo del 30%, disparará una alerta crítica a Dirección y Estudiante. |
| RF-25 | Orquestación de Feedback | El backend enviará asíncronamente un payload al ESP32 ordenando el color: Verde/Amarillo (Grupo correcto) o Rojo (Grupo incorrecto), mediante protocolo websocket. |

## Tabla 7: Requerimientos Funcionales - Dispositivo Periférico IoT en Puerta (ESP32 Firmware)

| Código | Nombre del Requerimiento | Descripción Operacional del Requerimiento |
|---|---|---|
| RF-27 | Estado Cíclico de Reposo | El firmware mantendrá el anillo LED mostrando una animación azul de baja intensidad en espera. |
| RF-28 | Confirmación Visual | El ESP32 conmutará el anillo LED: Verde (Asistió), Amarillo (Tardanza), Rojo (Denegado). |
| RF-29 | Disparo Acústico Sincronizado | El ESP32 excitará el buzzer: 1 Beep corto (Éxito), 2 Beeps (Tardanza), Tono sostenido (Error). |

## Ejemplo del horario de clases de un alumno

Aclara que las clases o el horario de clases en la universidad son de 7.00 AM a 20:00 PM, este solo es un ejemplo de como son los horarios del alumno, depende de como le va en el año para que sus horario de organize/desorganize


| Horario | Lunes | Martes | Miércoles | Jueves | Viernes |
|---|---|---|---|---|---|
| 07:00 - 08:00 | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) | ISA901 Computación Gráfica (LAB 401)<br>MAMANI VILCA, Eddy (Dr.) | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) | ISA901 Computación Gráfica (LAB 401)<br>MAMANI VILCA, Eddy (Dr.) | ISA904 Programación Paralela (LAB 304) |
| 08:00 - 09:00 | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) | ISA901 Computación Gráfica (LAB 401)<br>MAMANI VILCA, Eddy (Dr.) | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) | ISA901 Computación Gráfica (LAB 401)<br>MAMANI VILCA, Eddy (Dr.) | ISA901 Computación Gráfica (LAB 306)<br>MAMANI VILCA, Eddy (Dr.) |
| 09:00 - 10:00 | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) |
| 10:00 - 11:00 | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) | ISA905 Metodología de la Investigación Científica (LAB 305)<br>CARI INCAHUANACO, Francisco (Mag.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) | ISA902 Sistemas Distribuidos (LAB 304)<br>CONTRERAS SALAS, Lincol (Dr.) |
| 11:00 - 12:00 | ISA906 Interacción Humano Computador (LAB 304)<br>ROJAS ENRIQUEZ, Hermenegildo (Dr.) | Tutoría | ISA906 Interacción Humano Computador (LAB 304)<br>ROJAS ENRIQUEZ, Hermenegildo (Dr.) | ISA904 Programación Paralela (LAB 304) | ISA903 Inteligencia Artificial I (LAB 304)<br>AQUINO CRUZ, Mario (Mag.) |
| 12:00 - 13:00 | ISA906 Interacción Humano Computador (LAB 304)<br>ROJAS ENRIQUEZ, Hermenegildo (Dr.) | Tutoría | ISA906 Interacción Humano Computador (LAB 304)<br>ROJAS ENRIQUEZ, Hermenegildo (Dr.) | ISA904 Programación Paralela (LAB 304) | — |
| 13:00 - 14:00 | — | — | — | — | — |
| 14:00 - 15:00 | — | ISA904 Programación Paralela (LAB 306) | — | — | — |
| 15:00 - 16:00 | — | ISA904 Programación Paralela (LAB 306) | — | — | — |
