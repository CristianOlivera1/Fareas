# Sistema de asistencia con reconocimiento facial e IoT para aulas universitarias: diseño y validación

## Face recognition and IoT attendance system for university classrooms: design and validation

> **Revista Micaela** - ISSN: 2955-8646 (en línea) / 2709-8990 (impresa)
> Universidad Nacional Micaela Bastidas de Apurímac - Vicerrectorado de Investigación - Perú
> Edición especial FERCYT UNAMBA 2026 - Categoría D: Desarrollo Tecnológico
> *Versión anónima para el primer envío (doble ciego): sin nombres, ORCID, correos, filiación ni agradecimientos.*

---

## Resumen

**Objetivo.** Desarrollar y validar técnicamente un sistema de control de asistencia basado en reconocimiento facial e Internet de las Cosas (IoT) para las aulas de la Facultad de Ingeniería Informática y Sistemas de la Universidad Nacional Micaela Bastidas de Apurímac, con la finalidad de automatizar el registro de asistencia de los estudiantes, reducir el tiempo que los docentes dedican al llamado de lista y garantizar la trazabilidad del registro y la protección de los datos biométricos. **Metodología.** Investigación tecnológica aplicada bajo el enfoque de ciencia del diseño (*Design Science Research*). Se definieron 35 requerimientos funcionales y se desarrolló un sistema web con Angular, FastAPI y PostgreSQL, integrado con reconocimiento facial mediante SCRFD y ArcFace (512 dimensiones), que procesa video RTSP de una cámara IP en CPU y comunica el resultado mediante un nodo ESP32 en el acceso al aula. La evaluación contempló pruebas automatizadas, mediciones de latencia, verificación de requerimientos y un piloto con estudiantes. **Resultados principales.** Se aprobaron 544 de 547 pruebas automatizadas (tres fallaron por datos del entorno). Un cuadro completo se procesó con una mediana de 199 ms con el equipo en reposo y de 1,4 s con carga. Se corrigieron defectos de alineación facial y de configuración de hilos. La docente calificó el panel con 87,5 puntos de 100. [COMPLETAR: TAR, FAR y FRR.] **Conclusión principal.** El sistema cumple los requerimientos funcionales y opera sin GPU; la precisión con estudiantes reales dependerá del piloto.

**Palabras clave:** asistencia automatizada; reconocimiento facial; Internet de las cosas; ArcFace

## Abstract

**Objective.** To develop and technically validate an attendance control system based on face recognition and the Internet of Things (IoT) for the classrooms of the Faculty of Computer Engineering and Systems of the Micaela Bastidas National University of Apurímac, in order to automate student attendance recording, reduce the time teachers spend on roll call, and guarantee record traceability and the protection of biometric data. **Methodology.** Applied technological research under the Design Science Research approach. Thirty-five functional requirements were defined and a web system was developed with Angular, FastAPI and PostgreSQL, integrated with face recognition through SCRFD and ArcFace (512 dimensions); it processes the RTSP video of an IP camera on a CPU and reports the result through an ESP32 node at the classroom entrance. Evaluation included automated tests, latency measurements, requirement verification and a pilot with students. **Key findings.** 544 of 547 automated tests passed (three failed because of environment data). A full frame was processed in a median of 199 ms on an idle machine and 1.4 s under load. Alignment and thread-configuration defects were fixed. The teacher rated the panel 87.5 out of 100. [COMPLETE: pilot TAR, FAR and FRR.] **Main conclusion.** The system meets the functional requirements and runs without a GPU; recognition accuracy with real students will depend on the pilot.

**Keywords:** automated attendance; face recognition; Internet of Things; ArcFace

---

## 1. Introducción

Controlar la asistencia es una tarea cotidiana de la gestión académica universitaria, pero no es menor: sirve para seguir de cerca al estudiante y para cumplir las normas de la institución. Credé et al. (2010), en un metaanálisis, encontraron que asistir a clases se asocia de forma consistente con un mejor rendimiento académico. En la Universidad Nacional Micaela Bastidas de Apurímac (UNAMBA), además, el registro tiene efectos administrativos y académicos, ya que el Reglamento General Académico fija condiciones sobre las inasistencias y la evaluación de los estudiantes (Consejo Universitario de la UNAMBA, 2019). El pase de lista manual, sin embargo, resta tiempo a la clase, permite registros indebidos (por ejemplo, que un compañero responda por otro) y hace difícil detectar a tiempo las faltas acumuladas.

El aprendizaje profundo ha impulsado sistemas de reconocimiento facial capaces de identificar personas de forma automática. ArcFace, por ejemplo, produce representaciones del rostro que se comparan mediante medidas de similitud (Deng et al., 2022), y detectores como SCRFD localizan rostros en imágenes y video (Guo et al., 2021). En educación, Alhanaee et al. (2021) estudiaron un sistema de asistencia basado en reconocimiento facial y aprendizaje por transferencia, y Widyani et al. (2026) reportaron resultados de reconocimiento al combinar MTCNN y ArcFace en un entorno escolar. Estos trabajos confirman que la visión por computador puede aplicarse al registro de asistencia. Con todo, acertar con la identidad es solo una parte del problema: para que una institución use el sistema, el reconocimiento debe conectarse con las condiciones académicas y operativas en que se registra cada asistencia.

Un sistema de asistencia exige resolver más que la elección de un modelo de reconocimiento. Hay que comprobar que la persona identificada esté matriculada en el curso y en el grupo programados, aplicar las reglas de asistencia de la institución, conservar registros que puedan rastrearse y avisar con rapidez el resultado del reconocimiento. A esto se suman las limitaciones de infraestructura y la protección de los datos biométricos, cuyo tratamiento se rige por la normativa peruana de datos personales (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024). Una solución pensada para la universidad tiene que reunir en una sola arquitectura el procesamiento facial, la gestión académica, los dispositivos de comunicación y las medidas de protección de datos.

Este estudio parte de esa necesidad: un sistema de control de asistencia que combine reconocimiento facial, reglas académicas y comunicación con un dispositivo IoT, que funcione con infraestructura local y que no dependa de servicios externos de reconocimiento ni de procesadores gráficos. El aporte tecnológico consiste en integrar estos componentes para gestionar el registro de asistencias, tardanzas, inasistencias y justificaciones, y para informar el resultado del reconocimiento en la entrada del aula. La evaluación debía cubrir tres aspectos: el cumplimiento funcional, el rendimiento del procesamiento y el desempeño del reconocimiento facial en condiciones reales de uso.

El objetivo fue diseñar, desarrollar y evaluar técnicamente un sistema de control de asistencia basado en reconocimiento facial e Internet de las Cosas (IoT) para las aulas de la Facultad de Ingeniería Informática y Sistemas de la UNAMBA. Para lograrlo, se especificaron los requerimientos funcionales, se implementó el procesamiento facial en CPU, se integraron las reglas de asistencia y la señalización con un nodo ESP32, y se plantearon procedimientos de evaluación basados en pruebas automatizadas, mediciones de rendimiento y verificación funcional. También se definió un protocolo piloto con estudiantes para medir la precisión del reconocimiento y el funcionamiento del sistema; sus resultados indicarán cómo se comporta en condiciones reales.

## 2. Metodología

### 2.1 Tipo y diseño de la investigación

El estudio fue aplicado, cuantitativo y descriptivo: produjo y evaluó un artefacto (el sistema) y describió su funcionamiento con indicadores medibles. Se siguió la investigación en ciencia del diseño (*design science research*; Hevner et al., 2004) con las seis actividades de Peffers et al. (2007): identificación del problema, definición de objetivos, diseño y desarrollo, demostración, evaluación y comunicación.

### 2.2 Requerimientos

Los requerimientos se obtuvieron del análisis de la operación académica de la facultad y del Reglamento General Académico (cursos, grupos paralelos, bloques por aula, tolerancia de diez minutos y límite de 30 % de inasistencias; Consejo Universitario de la UNAMBA, 2019, arts. 74 y 75), y se formalizaron en 35 requerimientos funcionales (RF-01 a RF-35) agrupados en seis módulos: administración e infraestructura, estudiante y docente, procesamiento de imágenes, lógica de negocio y alertas, nodo IoT y trazabilidad. Las restricciones de diseño fueron: ejecución local en CPU, sin servicios de reconocimiento externos, sin entrenamiento de modelos y con un único proceso de servidor.

### 2.3 Diseño de la interfaz y del prototipo

El diseño de la interfaz se desarrolló mediante un prototipo de alta fidelidad en Figma (Figura 1), previo a la implementación del sistema web, con el propósito de definir y verificar la navegación, la disposición de los elementos y los principales flujos de interacción. El prototipo comprendió las interfaces de inicio de sesión, panel de control, horarios, grupos, docentes, aulas, estudiantes, usuarios, enrolamiento facial, feriados y perfil.

Para organizar la interfaz se aplicó el diseño atómico (*Atomic Design*), estructurando los componentes en átomos, moléculas, organismos y plantillas de página (Kurniawan, 2024). Esta organización permitió establecer elementos visuales básicos reutilizables, combinarlos en componentes de mayor complejidad y mantener una presentación coherente entre los distintos módulos del sistema. Posteriormente, esta estructura se trasladó a Angular mediante componentes autónomos, reutilización de estilos globales y una organización modular de la interfaz, lo que facilita su mantenimiento y la consistencia visual de la aplicación.

> **Figura 1 - imagen que debes subir.** Captura del tablero de Figma con todas las pantallas del prototipo (300 ppp, PNG). Título debajo: «**Figura 1** Prototipo de la interfaz del sistema en Figma».

### 2.4 Arquitectura del sistema

El sistema es una aplicación cliente-servidor de monolito modular: un cliente web de una sola página en Angular 21 y una API REST en FastAPI (Python 3.13) con acceso asíncrono a PostgreSQL 17 mediante SQLModel y control de acceso por rol (administrador, docente y estudiante). La cámara IP Hikvision de 4 MP, alimentada por PoE+, entrega por RTSP un flujo de 1280 × 720 píxeles a 15 cuadros por segundo (canal 102); el servidor lo procesa, registra la asistencia y comunica el veredicto al nodo de la puerta por WebSocket (Fette & Melnikov, 2011) y al panel web por eventos del servidor. El esquema relacional tiene 18 tablas; los *embeddings* se guardan en una columna `REAL[512]` y la similitud se calcula en NumPy. La Figura 2 muestra la arquitectura.

> **Figura 2 - imagen que debes subir.** El diagrama `docs/arquitectura-fareas.png` (cámara → switch PoE+ → PC servidor → router Wi-Fi → nodo ESP32; navegador del docente). Título debajo: «**Figura 2** Arquitectura general del sistema».

### 2.5 Canal de reconocimiento facial

El canal de visión usa modelos preentrenados en formato ONNX ejecutados en CPU con onnxruntime, como es habitual en el reconocimiento facial profundo (Wang & Deng, 2021); no se entrenó ningún modelo, y el «aprendizaje» del sistema es el enrolamiento de cada estudiante. Cada cuadro pasa por cuatro etapas:

1. **Detección.** Un detector SCRFD (Guo et al., 2021) localiza los rostros y estima cinco puntos de referencia (Minaee et al., 2021). La imagen se reescala conservando su proporción hasta un lado máximo de 640 píxeles, con dimensiones múltiplos de 32.
2. **Alineación.** Los cinco puntos definen una transformación de similitud hacia la plantilla canónica de 112 × 112 píxeles.
3. **Extracción.** Un modelo ArcFace con *backbone* ResNet-50 entrenado con WebFace600K, subconjunto depurado de WebFace260M (Deng et al., 2022; Zhu et al., 2021), produce un vector de 512 dimensiones normalizado en norma L2.
4. **Identificación.** La similitud entre el vector observado **q** y la plantilla **t** de cada candidato es el coseno, equivalente al producto punto:

$$s(\mathbf{q}, \mathbf{t}) = \mathbf{q} \cdot \mathbf{t} \qquad (1)$$

Un rostro se acepta como el estudiante *i* cuando se cumplen a la vez tres condiciones:

$$s_i \geq \tau \quad \wedge \quad s_i - \max_{j \neq i} s_j \geq \delta \quad \wedge \quad n_i \geq N \qquad (2)$$

donde τ es el umbral de similitud (0,55, configurable), δ el margen respecto del segundo mejor candidato (0,06) y *n_i* el número de cuadros consecutivos en que *i* fue el mejor candidato, que debe alcanzar *N* = 2 (unos 0,7 s a 3 cuadros por segundo por aula). El vector observado es el promedio normalizado de los *embeddings* de los últimos tres cuadros, y la ventana se reinicia si la similitud con el promedio previo es menor de 0,45 (otra persona). Solo se analiza el rostro de mayor área, y se descartan los de lado menor a 60 píxeles y los de perfil (desviación de la nariz mayor al 50 % de la distancia interocular); mientras tanto, el veredicto es «identificando» y no revela ninguna identidad.

La galería se mantiene en memoria y la búsqueda se restringe primero a los matriculados en el bloque vigente del aula; si el rostro es de un estudiante conocido pero no matriculado en ese bloque, el veredicto es acceso denegado.

### 2.6 Enrolamiento y protección de datos biométricos

Cada estudiante se enrola con tres a cinco fotografías frontales y su consentimiento expreso, obligatorio y registrado con fecha. Se rechazan las fotos sin exactamente un rostro, con rostro menor de 90 píxeles, baja confianza (< 0,6), cabeza girada o inclinada o desenfocadas. Con las fotos aceptadas se verifica su consistencia (similitud mínima de 0,40) y se guarda solo el promedio normalizado como plantilla (Widyani et al., 2026); si se parece (≥ 0,60) a la de otra cuenta activa, se rechaza y se nombra la cuenta coincidente. La fotografía de portada se guarda en almacenamiento privado con URL firmada, ambos datos se eliminan con una sola operación y toda acción sensible queda en una bitácora de auditoría, en línea con la minimización y los derechos de cancelación de la normativa peruana (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024).

### 2.7 Reglas de asistencia

Cada bloque horario genera una sesión que el planificador abre 15 minutos antes de su inicio y cierra al finalizar el bloque. La primera identificación válida del estudiante en la sesión se clasifica como:

$$
\text{estado} =
\begin{cases}
\text{asistió}, & t \leq t_0 + 10\ \text{min} \\
\text{tardanza}, & t_0 + 10\ \text{min} < t \leq t_f \\
\text{falta}, & \text{sin marca al cierre}
\end{cases} \qquad (3)
$$

donde *t* es la hora de la marca, *t₀* la de inicio y *t_f* la de fin del bloque; las marcas son únicas por estudiante y sesión, y al cierre se generan las faltas de los matriculados sin marca. El porcentaje acumulado de inasistencia es:

$$P = \frac{F}{S} \times 100 \qquad (4)$$

con *F* las faltas no justificadas y *S* las sesiones válidas realizadas. Se avisa cuando *P* ≥ 20 % y se notifica la inhabilitación cuando *P* > 30 %, una vez por nivel y con al menos cuatro sesiones realizadas; los umbrales de 10 minutos y de 30 % provienen del Reglamento (Consejo Universitario de la UNAMBA, 2019, arts. 74 y 75) y son configurables. Los docentes pueden rectificar estados y registrar justificaciones, con motivo obligatorio y bitácora.

### 2.8 Señalización en la puerta y monitoreo en vivo

El nodo de la puerta es un ESP32 con un anillo de 16 LED WS2812B y un zumbador activo. Recibe el veredicto por WebSocket y lo muestra con el semáforo del sistema: verde y un pitido (asistió), amarillo y dos pitidos (tardanza), rojo y tono sostenido (acceso denegado) y azul en silencio (sin clase o rostro no identificado).

El panel de monitoreo muestra el video de la cámara con latencia sub-segundo mediante WebRTC, servido por un repetidor de video local que convierte el flujo RTSP (con respaldo MJPEG), y dibuja sobre él un recuadro con esquinas cuyo color corresponde al veredicto vigente. La importación de horarios y nóminas usa reconocimiento óptico de caracteres basado en PP-OCR (Li et al., 2022) con una pantalla de revisión.

### 2.9 Procedimiento y plan de evaluación

La evaluación tuvo cuatro componentes: (1) **pruebas automatizadas** de la API y del cliente, contra la base de datos del entorno de desarrollo; (2) **mediciones de rendimiento** del canal de reconocimiento sobre 40 cuadros con rostro del video de demostración; (3) **verificación de requerimientos**; y (4) un **piloto con personas**, en el que se calculan las tasas de aceptación verdadera (TAR), de falsa aceptación (FAR) y de falso rechazo (FRR):

$$\text{FAR} = \frac{FA}{I}, \qquad \text{FRR} = \frac{FR}{G} = 1 - \text{TAR} \qquad (5)$$

donde *FA* son las aceptaciones erróneas de intentos impostores (*I*) y *FR* los rechazos de intentos genuinos (*G*). La usabilidad del panel se mide con la Escala de Usabilidad del Sistema (SUS; 10 ítems de 1 a 5, puntaje de 0 a 100 y media de referencia de 68; Lewis, 2018) aplicada a la docente que lo opera, y la experiencia de los estudiantes en la puerta, con un cuestionario de percepción de seis ítems. Los hallazgos se organizan según ISO/IEC 25010:2023 (International Organization for Standardization & International Electrotechnical Commission [ISO/IEC], 2023).

## 3. Resultados

### 3.1 Cumplimiento de los requerimientos y pruebas automatizadas

Para verificar el sistema se partió de los 35 requerimientos funcionales definidos durante el desarrollo (RF-01 a RF-35), formulados conforme a las prácticas de ingeniería de requisitos (ISO/IEC/IEEE, 2018). A cada uno se le asignó la funcionalidad que lo implementaba y se comprobó que funcionara, ya fuera con una prueba automatizada o con una verificación funcional documentada. Así fue posible revisar si lo que se había especificado coincidía con lo que el sistema realmente hacía.

En la versión final se corrieron pruebas automatizadas tanto en el servidor como en el cliente web. Las del servidor cubrían autenticación, catálogos, matrícula, reglas de asistencia, sesiones, justificaciones, seguridad, comunicación por WebSocket (Fette & Melnikov, 2011), reportes y procesamiento de visión, y se ejecutaron contra la base de datos del entorno de desarrollo. De las 403 pruebas, repartidas en 44 archivos, 400 resultaron aprobadas y ninguna se omitió, porque la corrida se hizo en día laborable. Las otras tres no pasaron: dos hacían referencia al dispositivo de ejemplo esp32-lab305, que no existía en la base de datos de pruebas, y una de reportes por docente no coincidió con los datos que el entorno de pruebas tenía en ese momento. En el cliente web, las 144 pruebas, organizadas en 33 archivos, se aprobaron sin excepción. El sistema comprende 15 635 líneas de Python en el servidor y 15 004 de TypeScript en el cliente, y expone 125 rutas de API sobre 18 tablas.

Las verificaciones técnicas también llevaron a modificar el diseño. El detector YOLO que se había previsto al inicio (Redmon et al., 2016) se reemplazó por SCRFD para la detección facial (Guo et al., 2021), y se recalibraron tanto los parámetros de decisión del reconocimiento, basado en representaciones faciales de tipo ArcFace (Deng et al., 2022), como la regla de tardanza. La implementación evaluada ya incluye estos cambios. Respecto al componente IoT, la comunicación entre el servidor y el nodo ESP32 se probó primero con un simulador de WebSocket y después con el nodo físico instalado en la puerta del aula durante el piloto (Sección 3.4).

Los resultados indican que cada funcionalidad del sistema tiene una prueba o una verificación documentada, y que la suite del cliente se ejecutó sin fallos. En el servidor, en cambio, quedaron tres pruebas sin aprobar, por datos del entorno de prueba y no por el reconocimiento facial. Por eso, lo que aquí se presenta es evidencia de verificación técnica del software, no una demostración de que todos los requerimientos funcionen en condiciones reales. El desempeño del reconocimiento con estudiantes se reporta en la Sección 3.4.

### 3.2 Rendimiento del canal de reconocimiento

Los tiempos medidos se presentan en la Tabla 1. En la corrida con el equipo en reposo, un cuadro completo (detección, alineación, extracción e identificación) tomó una mediana de 199 ms, compatible con los 3 cuadros por segundo por aula (intervalo de 333 ms); en cinco corridas con el equipo cargado (sincronización de archivos, navegador y otros procesos) la mediana fue de 1,4 s, por lo que el rendimiento depende de que el procesador no esté disputado. La búsqueda entre 5 000 plantillas, un orden de magnitud superior al de una facultad, tomó menos de 2 ms, sin necesidad de un índice vectorial.

**Tabla 1**
**Latencias del canal de reconocimiento (40 cuadros, solo CPU)**

| Etapa | En reposo: mediana / P95 (ms) | Con carga: mediana / P95 (ms) |
| --- | --- | --- |
| Detección facial (SCRFD) | 77,7 / 329,9 | 227,3 / 297,6 |
| Extracción de *embedding* (ArcFace R50) | 117,0 / 1 774,6 | 1 136,7 / 1 331,1 |
| Búsqueda entre 5 000 plantillas | 1,4 / 2,9 | 1,9 / 2,4 |
| Cuadro completo (detección, extracción y búsqueda) | 198,6 / 2 078,4 | 1 377,6 / 1 569,6 |

*Nota.* Elaboración propia. Procesador Intel Core de 12.ª generación (12 hilos), sin GPU; cuatro hilos por modelo y sin espera activa; cuadros de 720 × 1280 del video de demostración. «En reposo» es una corrida; «con carga» es la mediana de cinco corridas en prioridad alta. El percentil 95 en reposo refleja una interrupción puntual. «Cuadro completo» repite detección y extracción, por lo que no es la suma de las filas.

Con la cámara IP real (flujo de 1280 × 720 a 15 cuadros por segundo) el sistema detectó rostros en vivo (Figura 3); el rostro de una captura de verificación midió 106 píxeles con confianza de 0,82. El video del panel pasó de un retraso acumulado a una reproducción fluida con WebRTC.

> **Figura 3 - imagen que debes subir.** Captura del panel «Actividad en tiempo real» con el recuadro de esquinas sobre el rostro y el veredicto (difumina rostro y nombre si no hay consentimiento). Título debajo: «**Figura 3** Panel de monitoreo en vivo con el recuadro facial y el veredicto».

### 3.3 Defectos detectados durante la validación

La integración con la cámara real permitió corregir los defectos de la Tabla 2. El principal fue la decodificación de los puntos de referencia faciales con el signo invertido: en un cuadro de prueba la boca quedaba sobre los ojos, lo que giraba la alineación casi 180° y explicaba que se rechazaran fotos frontales por «cabeza inclinada»; tras la corrección los puntos quedaron en orden anatómico dentro del recuadro y se añadió una prueba de regresión sobre el video de demostración. Una segunda revisión mostró que, con el servidor activo, los hilos de cada modelo quedaban en espera activa: la mediana por cuadro era de 1 115 ms (percentil 95 de 14 s) y bajó a 157 ms al limitar los hilos a cuatro y desactivar la espera activa. También se corrigieron el reescalado sin conservar la proporción, el umbral configurable ignorado y el retraso del video.

**Tabla 2**
**Defectos principales detectados en la validación y su corrección**

| N.° | Defecto y efecto | Corrección | Verificación |
| --- | --- | --- | --- |
| 1 | Signo invertido en los puntos de referencia: alineación errónea y reconocimiento poco fiable | Suma de distancias al ancla | Prueba de regresión sobre video real |
| 2 | Decisión con un solo cuadro y sin margen: riesgo de falsas aceptaciones | Margen δ, promedio, confirmación en *N* cuadros, tamaño mínimo y descarte de perfiles (Ecuación 2) | Pruebas unitarias |
| 3 | Hilos en espera activa: 1 115 ms de mediana por cuadro | Cuatro hilos y sin espera activa | Medición comparativa (157 ms) |
| 4 | Veredicto provisional con identidad: el panel mostraba nombre y código sin confirmar | El veredicto «identificando» no lleva identidad | Prueba unitaria y revisión del panel |

*Nota.* Elaboración propia.

### 3.4 Piloto: protocolo y resultados parciales

El piloto se realizó con 20 estudiantes, pero sus datos aún no se han procesado, por lo que **la precisión del reconocimiento con estudiantes reales no se reporta en esta versión**. La docente operó el panel web y respondió, el 28 de octubre de 2026, el SUS y tres preguntas abiertas; las Tablas 3 y 4 conservan [COMPLETAR] en lo que depende de esos datos.

> **Protocolo.** Una sola prueba, en el horario de un curso de la docente asesora, con los 26 estudiantes del grupo, de los cuales 20 aceptaron participar y firmaron el consentimiento; solo ellos se enrolan (3 a 5 fotos) y hacen 6 capturas frente a la cámara (3 normales y 3 con luz lateral o lentes), con el equipo instalado temporalmente. Al menos cinco personas no enroladas hacen 3 capturas cada una para estimar la falsa aceptación. Durante el bloque, el sistema funciona en paralelo al registro manual de la docente, tomado como verdad de terreno, y al final los estudiantes responden un cuestionario de percepción de seis ítems. Los datos se analizan con códigos, solo se guardan valores de similitud (sin imágenes ni video), las plantillas se eliminan al terminar y los resultados se resumen con intervalos de Wilson al 95 %. **[CONFIRMAR: ajusta este párrafo a lo realmente hecho.]**

La docente asignó 5, 1, 5, 1, 5, 1, 5, 1, 4 y 5 puntos a los ítems 1 a 10, de modo que los impares aportaron 19 puntos y los pares 16; el SUS fue 35 × 2,5 = 87,5 sobre 100, por encima de la media de 68 (Lewis, 2018). Solo el ítem 10 (necesitar saber varias cosas antes de empezar) fue desfavorable. En las preguntas abiertas describió el panel como sencillo, no muy distinto de su hoja de cálculo en línea habitual, con la ventaja de los reportes agrupados y las tendencias; propuso un enlace público de consulta para los estudiantes, señaló la caída de Internet como riesgo excepcional y no cambiaría nada antes del uso oficial.

**Tabla 3**
**Desempeño de reconocimiento en el piloto (por completar)**

| Indicador | Valor |
| --- | --- |
| Participantes enrolados (de 26 estudiantes del grupo) | 20 |
| Intentos genuinos (*G*) | [COMPLETAR] |
| Intentos impostores (*I*) | [COMPLETAR] |
| Tasa de aceptación verdadera (TAR) | [COMPLETAR] |
| Tasa de falsa aceptación (FAR) | [COMPLETAR] |
| Tasa de falso rechazo (FRR) | [COMPLETAR] |
| Tiempo medio hasta el veredicto en la puerta (s) | [COMPLETAR] |

*Nota.* Se calculan con la Ecuación 5 con el umbral τ = 0,55 y con otros dos valores de τ para analizar el compromiso entre FAR y FRR.

**Tabla 4**
**Usabilidad y calidad percibida (resultados parciales)**

| Instrumento | Participantes | Resultado |
| --- | --- | --- |
| Escala de Usabilidad del Sistema del panel web (docente) | 1 | 87,5 puntos de 100 (SUS) |
| Percepción de los estudiantes en la puerta (mediana por ítem, escala 1 a 5) | [COMPLETAR] | [COMPLETAR] |
| Veredictos correctos en la puerta (ESP32 físico) | 20 | 20 de 20 en verde (asistió) |
| Concordancia con la asistencia manual (porcentaje y kappa de Cohen) | [COMPLETAR] | [COMPLETAR] |

*Nota.* Todos los participantes llegaron puntuales, por lo que solo se probó el veredicto verde. El SUS (Lewis, 2018) lo respondió una sola usuaria, la docente asesora, y es descriptivo; la percepción de los estudiantes proviene de un cuestionario propio, exploratorio y sin validación formal.

## 4. Discusión

### 4.1 Interpretación de los resultados

El sistema cumple los requerimientos funcionales y, con el procesador libre, un cuadro completo (mediana de 199 ms) cabe en el intervalo de 333 ms entre cuadros; con carga tardó 1,4 s, por lo que el servidor debe dedicarse al sistema o reducirse la frecuencia, y para varias aulas habría que repartir el trabajo. La búsqueda entre 5 000 plantillas en menos de 2 ms basta a la escala de una facultad; los índices aproximados, pensados para miles de millones de vectores (Johnson et al., 2021), aún no se justifican.

El hallazgo más importante fue un defecto de alineación (Tabla 2): en un canal implementado a mano, un error de preprocesamiento no lanza una excepción sino que degrada la precisión en silencio, y solo se vio al contrastar los puntos con el rostro en video real; por eso la prueba de regresión geométrica sobre video real es una aportación metodológica. La revisión de la velocidad mostró algo parecido: el mayor costo estaba en la configuración de ejecución y no en los modelos.

La docente calificó el panel con 87,5 de 100, lo que sugiere una interfaz fácil de aprender, coherente con el prototipo (Sección 2.3). Proviene de una sola persona, además asesora, y no prueba que se reduzca el tiempo del llamado de lista, que no se midió: ella destacó los reportes y las tendencias más que el ahorro.

### 4.2 Comparación con estudios previos

A diferencia de los sistemas reportados, centrados en el modelo y su exactitud (Alhanaee et al., 2021; Widyani et al., 2026), este trabajo integra el reconocimiento con las reglas académicas de una universidad peruana (grupos paralelos, bloques, matrícula, tolerancia, justificaciones y alertas de inhabilitación). Coincide con Widyani et al. (2026) en usar ArcFace con ResNet-50 y plantilla promedio, pero sus cifras (92,86 % de exactitud y 4,76 % de falsa aceptación) aún no son comparables con el piloto (Tabla 3). Sí lo son las decisiones: aquí la FAR se controla con el margen δ, el promedio y la confirmación en varios cuadros (Ecuación 2).

### 4.3 Implicaciones

En lo práctico, la solución usa equipamiento común y no depende de servicios externos, lo que reduce costos y mantiene los datos biométricos bajo control institucional. En lo normativo, el consentimiento obligatorio, el almacenamiento de plantillas y no de imágenes, la eliminación a solicitud y la bitácora de auditoría se alinean con la normativa de datos personales (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024). En lo académico, el estudiante ve su porcentaje de inasistencia y el docente cuenta con rectificación auditable; la consulta pública sugerida por la docente exigiría mostrar solo códigos.

### 4.4 Limitaciones

Las limitaciones son siete. Primero, la precisión con estudiantes reales aún no se reporta, por lo que los resultados son evidencia técnica y no de desempeño biométrico. Segundo, no hay detección de vida (*liveness*), así que una fotografía o pantalla podría suplantar a un estudiante (Yu et al., 2023). Tercero, el desempeño puede variar entre grupos demográficos (Grother et al., 2019). Cuarto, las latencias se midieron en un solo equipo, con un video de demostración, y variaron entre 0,2 y 1,4 s según la carga, por lo que el servidor debe estar dedicado; tampoco se probaron varias aulas, y el nodo ESP32 solo mostró el veredicto verde. Quinto, el piloto fue de una sola vez, en un curso, con instalación temporal, una sola usuaria para el SUS (la asesora, con posible sesgo a favor) y un cuestionario propio y exploratorio. Sexto, no se midió el tiempo ahorrado en el llamado de lista, finalidad declarada, y el sistema depende de la red: sin conexión no registra, por lo que debe mantenerse la rectificación manual. Séptimo, el reglamento impide el ingreso pasada la tolerancia de diez minutos (Consejo Universitario de la UNAMBA, 2019, art. 75), mientras que el sistema lo registra como tardanza; la regla es configurable y debe acordarse con la facultad.

### 4.5 Líneas futuras

Se proponen: (a) completar el análisis del piloto y ampliarlo a más aulas, reportando TAR, FAR y FRR con intervalos de confianza; (b) incorporar detección de vida; (c) evaluar modelos que adaptan el margen a la calidad de la imagen, como AdaFace (Kim et al., 2022); (d) evaluar el producto con ISO/IEC 25010:2023; (e) medir varias aulas concurrentes y el tiempo de llamado de lista con y sin el sistema; y (f) ofrecer una consulta pública de solo lectura con códigos en lugar de nombres.

## 5. Conclusiones

1. Se diseñó e implementó un sistema de asistencia con reconocimiento facial e IoT para la Facultad de Ingeniería Informática y Sistemas de la UNAMBA que cumple los 35 requerimientos funcionales.
2. El reconocimiento se ejecuta en CPU en una mediana de 199 ms por cuadro con el equipo en reposo (1,4 s con carga) y busca entre 5 000 plantillas en menos de 2 ms, lo que permite 3 cuadros por segundo por aula sin GPU si el servidor no está saturado.
3. La validación con la cámara real permitió corregir defectos de alineación facial y de configuración de hilos, y se incorporaron criterios de decisión más estrictos.
4. La docente calificó la usabilidad del panel con 87,5 de 100 (SUS, una sola usuaria).
5. La precisión con estudiantes reales se reportará al procesar los datos del piloto.

## Biografías

> *Nota para los autores: las normas piden este texto (60 palabras como máximo por autor) en la versión final; omítelo en el primer envío anónimo, como indica el bloque de notas.*

**Cristian Olivera Chávez.** Estudiante de la Universidad Nacional Micaela Bastidas de Apurímac, Perú, y desarrollador de software con experiencia en Angular, Next.js, Tailwind CSS, Laravel y Spring Boot. En este trabajo desarrolló el sistema web, la integración del reconocimiento facial y la comunicación con el nodo IoT. **[CONFIRMAR: carrera, ciclo y áreas de interés.]**

**[Segundo autor: agregar su biografía, 60 palabras como máximo.]**

## Declaración de uso de inteligencia artificial generativa

Se utilizó una herramienta de inteligencia artificial generativa (Claude, de Anthropic) como asistente en la programación del sistema y en la redacción y revisión de este manuscrito. Los autores revisaron, verificaron y asumen la responsabilidad del contenido. **[CONFIRMAR: ajusta esta declaración a las secciones exactas en que la usaste, por ejemplo «Introducción, Metodología y Discusión» y «código del sistema».]**

## Declaración de conflicto de interés

Los autores declaran no tener conflictos de interés. **[CONFIRMAR]**

## Declaración ética

Las pruebas técnicas descritas no involucraron la recolección de datos biométricos de terceros. De los 26 estudiantes del grupo, 20 firmaron el consentimiento y solo ellos participaron. La prueba con estudiantes se realizó con participación voluntaria, consentimiento informado por escrito de cada estudiante y autorización de la docente del curso, con datos seudonimizados y eliminación de las plantillas faciales al finalizar, conforme a los principios de la Ley N.° 29733 y su reglamento. No se tramitó la aprobación de un comité de ética institucional. **[CONFIRMAR]**

---

## Referencias

Alhanaee, K., Alhammadi, M., Almenhali, N., & Shatnawi, M. (2021). Face recognition smart attendance system using deep transfer learning. *Procedia Computer Science, 192*, 4093–4102. https://doi.org/10.1016/j.procs.2021.09.184

Credé, M., Roch, S. G., & Kieszczynka, U. M. (2010). Class attendance in college: A meta-analytic review of the relationship of class attendance with grades and student characteristics. *Review of Educational Research, 80*(2), 272–295. https://doi.org/10.3102/0034654310362998

Consejo Universitario de la Universidad Nacional Micaela Bastidas de Apurímac. (2019, 14 de noviembre). *Reglamento General Académico de la UNAMBA* (Resolución N.° 471-2019-CU-UNAMBA). Universidad Nacional Micaela Bastidas de Apurímac. https://cdn.www.gob.pe/uploads/document/file/8392692/6978325-resolucion-n-471-20219-cu-unamba%282%29.pdf?v=1783351594

Decreto Supremo N.° 016-2024-JUS. (2024, 30 de noviembre). Decreto Supremo que aprueba el Reglamento de la Ley N.° 29733, Ley de Protección de Datos Personales. *El Peruano*. https://www.gob.pe/institucion/anpd/normas-legales/6554453-n-016-2024-jus

Deng, J., Guo, J., Yang, J., Xue, N., Kotsia, I., & Zafeiriou, S. (2022). ArcFace: Additive angular margin loss for deep face recognition. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 44*(10), 5962–5979. https://doi.org/10.1109/TPAMI.2021.3087709

Fette, I., & Melnikov, A. (2011). *The WebSocket protocol* (RFC 6455). Internet Engineering Task Force. https://doi.org/10.17487/RFC6455

Grother, P., Ngan, M., & Hanaoka, K. (2019). *Face recognition vendor test (FRVT) part 3: Demographic effects* (NISTIR 8280). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.IR.8280

Guo, J., Deng, J., Lattas, A., & Zafeiriou, S. (2021). *Sample and computation redistribution for efficient face detection*. arXiv. https://doi.org/10.48550/arXiv.2105.04714

Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). Design science in information systems research. *MIS Quarterly, 28*(1), 75–105. https://doi.org/10.2307/25148625

International Organization for Standardization & International Electrotechnical Commission. (2023). *ISO/IEC 25010:2023. Systems and software engineering - Systems and software Quality Requirements and Evaluation (SQuaRE) - Product quality model* (2nd ed.). https://www.iso.org/standard/78176.html

ISO/IEC/IEEE. (2018). *ISO/IEC/IEEE 29148:2018. Systems and software engineering - Life cycle processes - Requirements engineering* (2nd ed.). https://www.iso.org/standard/72089.html

Johnson, J., Douze, M., & Jégou, H. (2021). Billion-scale similarity search with GPUs. *IEEE Transactions on Big Data, 7*(3), 535–547. https://doi.org/10.1109/TBDATA.2019.2921572

Kim, M., Jain, A. K., & Liu, X. (2022). AdaFace: Quality adaptive margin for face recognition. In *2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 18729–18738). IEEE. https://doi.org/10.1109/CVPR52688.2022.01819

Kurniawan, R. A. (2024). Pembuatan design system menggunakan pendekatan atomic design dan A/B testing. *Jurnal Teknologi dan Sistem Informasi Bisnis, 6*(3), 543–549. https://doi.org/10.47233/jteksis.v6i3.1346

Lewis, J. R. (2018). The System Usability Scale: Past, present, and future. *International Journal of Human–Computer Interaction, 34*(7), 577–590. https://doi.org/10.1080/10447318.2018.1455307

Ley N.° 29733. (2011, 3 de julio). Ley de Protección de Datos Personales. *El Peruano*. https://cdn.www.gob.pe/uploads/document/file/272360/Ley%20N%C2%BA%2029733.pdf.pdf?v=1618338779

Li, C., Liu, W., Guo, R., Yin, X., Jiang, K., Du, Y., Du, Y., Zhu, L., Lai, B., Hu, X., Yu, D., & Ma, Y. (2022). *PP-OCRv3: More attempts for the improvement of ultra lightweight OCR system*. arXiv. https://doi.org/10.48550/arXiv.2206.03001

Minaee, S., Luo, P., Lin, Z., & Bowyer, K. (2021). *Going deeper into face detection: A survey*. arXiv. https://doi.org/10.48550/arXiv.2103.14983

Peffers, K., Tuunanen, T., Rothenberger, M. A., & Chatterjee, S. (2007). A design science research methodology for information systems research. *Journal of Management Information Systems, 24*(3), 45–77. https://doi.org/10.2753/MIS0742-1222240302

Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You only look once: Unified, real-time object detection. In *2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 779–788). IEEE. https://doi.org/10.1109/CVPR.2016.91

Wang, M., & Deng, W. (2021). Deep face recognition: A survey. *Neurocomputing, 429*, 215–244. https://doi.org/10.1016/j.neucom.2020.10.081

Widyani, S. P., Suroso, S., & Taqwa, A. (2026). Real-time student attendance recognition using a centroid based MTCNN–ArcFace framework. *Edumatic: Jurnal Pendidikan Informatika, 10*(2), 360–369. https://doi.org/10.29408/edumatic.v10i2.35448

Yu, Z., Qin, Y., Li, X., Zhao, C., Lei, Z., & Zhao, G. (2023). Deep learning for face anti-spoofing: A survey. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 45*(5), 5609–5631. https://doi.org/10.1109/TPAMI.2022.3215850

Zhu, Z., Huang, G., Deng, J., Ye, Y., Huang, J., Chen, X., Zhu, J., Yang, T., Lu, J., Du, D., & Zhou, J. (2021). WebFace260M: A benchmark unveiling the power of million-scale deep face recognition. In *2021 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 10487–10497). IEEE. https://doi.org/10.1109/CVPR46437.2021.01035


---

## NOTAS PARA LOS AUTORES (eliminar este bloque antes de enviar)

1. **Formato:** las normas piden el envío en Word (`titulo_corto.docx`) siguiendo la plantilla oficial; este `.md` es el contenido. Al pasarlo a Word, verifica que el manuscrito quede entre 8 y 14 páginas (incluye tablas, figuras y referencias).
2. **Doble ciego:** esta versión no incluye nombres, ORCID, correos, filiaciones ni agradecimientos. La sección «Biografías» se agregó a pedido tuyo; las normas la piden para la versión final, así que elimínala (y el nombre de cualquier autor) del primer envío anónimo. Tampoco aparece el nombre de la docente que respondió el cuestionario. Cuando el artículo sea aceptado, la plantilla pide los datos completos de cada autor, el DOI y las fechas.
3. **FERCYT categoría D:** las bases piden además la constancia de aprobación para publicación del Fondo Editorial, la solicitud de admisión (Anexo 08), la constancia de matrícula del responsable, la constancia de inducción y la carta del asesor (Anexo 09). Recepción del artículo: 5 y 6 de noviembre de 2026, en mesa de partes.
4. **Producto y evidencia:** la categoría D exige artículo + prototipo/software. Prepara la demostración para la sustentación (20 puntos), incluidas las pruebas del nodo ESP32 físico.
5. **Resultados por completar:** Tabla 3 y las filas de percepción de estudiantes y concordancia de la Tabla 4 (datos del piloto), los resultados de la encuesta de estudiantes, las figuras 1 a 3, el resumen de resultados del piloto y las declaraciones marcadas con [CONFIRMAR]. El SUS de la docente ya está incorporado (87,5; una sola usuaria). Enlace de Figma: no se incluye en el manuscrito anónimo porque el archivo público puede mostrar el nombre del propietario; agrégalo cuando el artículo sea aceptado y se soliciten los datos completos: https://www.figma.com/design/G9ThNSqAy3N22tD0YPfJly/Dise%C3%B1o-proyecto Sin el piloto, el criterio «Evaluación y validación» (20 puntos) queda sustentado solo por la evidencia técnica.
6. **Referencias:** las 24 referencias fueron verificadas con Crossref, arXiv, el portal de la revista, el portal oficial gob.pe o la ficha de ISO; 14 de las 24 son de 2021 a 2026 (58 %). Para ahorrar páginas se quitaron las RFC de RTSP, WebRTC, JWT y Argon2 (se conserva la de WebSocket, que la docente citó). Por pedido de la docente se agregaron Kurniawan (2024; es el artículo del DOI 10.47233/jteksis.v6i3.1346, que ella rotuló «Frost»; el diseño atómico es de Brad Frost, pero el DOI corresponde a ese estudio), ISO/IEC/IEEE 29148:2018 y Redmon et al. (2016). No se agregó la versión de ArcFace de CVPR 2019 (DOI 10.1109/CVPR.2019.00482) porque el texto cita Deng et al. (2022), que es la versión de TPAMI ya incluida. Las normas piden mínimo 18 y 50 % de los últimos cinco años. Las RFC y los documentos de arXiv son normas técnicas y preprints; si prefieres solo fuentes en Scopus/Web of Science, sustitúyelos. El Reglamento General Académico de la UNAMBA (Res. 471-2019-CU) se citó a partir de la copia del documento (arts. 74 a 76, p. 18); el enlace público es el del portal gob.pe; falta verificar que los artículos citados no hayan sido modificados (una resolución posterior del Consejo Universitario modificó los arts. 52 y 53, no los citados aquí, pero conviene confirmarlo).
7. **Similitud:** el límite es 25 % sin contar citas y referencias. Revisa el manuscrito con tu software antiplagio antes de enviarlo.
8. **Inteligencia artificial:** las normas exigen declarar el uso de IA generativa y las secciones donde se usó. Ajusta la declaración a la realidad.
9. **Número de autores y contribuciones:** recomendado máximo 6; todos deben haber contribuido sustancialmente y aprobar la versión final.
