# Sistema de asistencia con reconocimiento facial e IoT para aulas universitarias: diseño y validación

## Face recognition and IoT attendance system for university classrooms: design and validation

> **Revista Micaela** — ISSN: 2955-8646 (en línea) / 2709-8990 (impresa)
> Universidad Nacional Micaela Bastidas de Apurímac — Vicerrectorado de Investigación — Perú
> Edición especial FERCYT UNAMBA 2026 — Categoría D: Desarrollo Tecnológico
> *Versión anónima para el primer envío (doble ciego): sin nombres, ORCID, correos, filiación ni agradecimientos.*

---

## Resumen

**Objetivo.** Se desarrolló y validó técnicamente un sistema de asistencia con reconocimiento facial e Internet de las cosas para las aulas de la Facultad de Informática de la Universidad Nacional Micaela Bastidas de Apurímac, con el fin de reemplazar el pase de lista manual por un registro automático, auditable y respetuoso con los datos biométricos. **Metodología.** Investigación tecnológica aplicada con enfoque de ciencia del diseño. Se especificaron 35 requerimientos funcionales y se construyó un sistema web (Angular, FastAPI y PostgreSQL) que procesa en CPU el video RTSP de una cámara IP mediante un detector SCRFD y un modelo ArcFace de 512 dimensiones, y que informa el veredicto en la puerta con un nodo ESP32. La evaluación combinó pruebas automatizadas, mediciones de latencia, verificación de requerimientos y un protocolo de piloto. **Resultados principales.** Se aprobaron 522 de 532 pruebas automatizadas (8 omitidas y 2 fallidas por un dato de entorno). Un cuadro completo se procesó con una mediana de 440 ms y la búsqueda entre 5 000 plantillas tomó 1,1 ms. En la integración con la cámara real se detectó y corrigió un defecto en los puntos de referencia faciales que degradaba la alineación. **Conclusión principal.** El sistema cumple los requerimientos funcionales y opera sin GPU a unos 2 cuadros por segundo por aula; la precisión con estudiantes reales depende del piloto propuesto.

**Palabras clave:** asistencia automatizada; reconocimiento facial; Internet de las cosas; ArcFace

## Abstract

**Objective.** A face recognition and Internet-of-Things attendance system was developed and technically validated for the classrooms of the Faculty of Informatics at the Micaela Bastidas National University of Apurímac, aiming to replace manual roll calls with an automatic, auditable record that respects biometric data protection. **Methodology.** Applied technological research was carried out following a design science approach. Thirty-five functional requirements were specified and a web system (Angular, FastAPI and PostgreSQL) was built; it processes the RTSP video of an IP camera on a CPU using an SCRFD face detector and a 512-dimensional ArcFace model, and reports the verdict at the door through an ESP32 node with an LED ring and a buzzer. Evaluation combined automated tests, latency measurements, verification against the requirements and a pilot protocol with people. **Key findings.** 522 of 532 automated tests passed (378 of 388 on the server and 144 of 144 on the client; 8 skipped and 2 failed because of an environment data issue); processing a complete frame took a median of 440 ms on a general-purpose processor, and an identity search among 5,000 templates took a median of 1.1 ms. During integration with the real camera, a defect in the decoding of facial landmarks that degraded alignment was detected and fixed, and a regression test was added. **Main conclusion.** The system meets the functional requirements and runs in real time without a GPU; recognition accuracy with real students depends on the pilot described.

**Keywords:** automated attendance; face recognition; Internet of Things; ArcFace

---

## 1. Introducción

La asistencia a clases es un insumo central de la gestión académica universitaria: un metaanálisis encontró que se relaciona de forma consistente con las calificaciones y que predice el rendimiento mejor que los puntajes de ingreso y los hábitos de estudio (Credé et al., 2010). En la UNAMBA, el Reglamento General Académico dispone que el estudiante con más del 30 % de inasistencia no puede ser evaluado, salvo casos justificados, y que el docente debe llevar el control de asistencia (Consejo Universitario de la UNAMBA, 2019, arts. 74 y 76). Sin embargo, el registro manual consume tiempo de clase, admite suplantaciones, como la firma de un compañero ausente, y dificulta calcular a tiempo el porcentaje acumulado de faltas, dato que permite prevenir una inhabilitación.

Los avances del aprendizaje profundo hicieron viable automatizar este registro. Las funciones de pérdida con márgenes angulares y los conjuntos de millones de rostros elevaron la exactitud del reconocimiento a niveles aplicables fuera del laboratorio (Wang & Deng, 2021): ArcFace produce incrustaciones (*embeddings*) comparables por similitud coseno (Deng et al., 2022), entrenadas con colecciones como WebFace260M (Zhu et al., 2021), y detectores livianos como SCRFD localizan rostros en tiempo real (Guo et al., 2021; Minaee et al., 2021). En asistencia se han propuesto sistemas con aprendizaje por transferencia (Alhanaee et al., 2021) y uno reciente con MTCNN y ArcFace con plantilla promedio (centroide) por persona reportó, en una escuela secundaria, una exactitud de 92,86 %, una tasa de falsa aceptación de 4,76 % y una de falso rechazo de 2,38 % (Widyani et al., 2026). Sus autores advierten que muchos sistemas se evalúan solo con conjuntos de referencia y rara vez en entornos educativos reales.

Persiste, por tanto, una brecha: son escasos los desarrollos que integran en una solución operativa el reconocimiento facial, las reglas académicas de la universidad (horarios, grupos, tolerancia, límite de inasistencias), la señalización física en la puerta y la protección de datos personales. En el contexto peruano esto es relevante porque las clases se organizan en cursos con grupos paralelos y matrículas por grupo, por lo que una detección solo tiene sentido si se valida contra la matrícula y el horario vigentes, y porque la imagen facial procesada para identificar a una persona es un dato biométrico sensible cuyo tratamiento exige consentimiento y medidas de seguridad (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024); el sistema debe, por tanto, minimizar los datos que conserva y permitir su eliminación.

El problema que aborda este trabajo es la ausencia, en las aulas de la Facultad de Informática de la UNAMBA, de un mecanismo automático de asistencia que combine reconocimiento facial, reglas académicas y trazabilidad con infraestructura local de bajo costo, sin servicios en la nube ni procesadores gráficos. El **objetivo general** fue diseñar, construir y validar técnicamente un sistema de asistencia con reconocimiento facial e IoT para esas aulas. Los **objetivos específicos** fueron: (a) especificar los requerimientos funcionales a partir del reglamento y la operación de la facultad; (b) implementar el canal de reconocimiento con ejecución en CPU; (c) implementar las reglas de asistencia, el monitoreo en vivo y la señalización en la puerta; y (d) evaluar el sistema con pruebas automatizadas, mediciones de rendimiento, verificación de requerimientos y un protocolo de piloto con estudiantes.

## 2. Metodología

### 2.1 Tipo y diseño de la investigación

El estudio fue aplicado, cuantitativo y descriptivo: produjo y evaluó un artefacto (el sistema) y describió su funcionamiento con indicadores medibles. Se siguió la investigación en ciencia del diseño (*design science research*; Hevner et al., 2004) con las seis actividades de Peffers et al. (2007): identificación del problema, definición de objetivos, diseño y desarrollo, demostración, evaluación y comunicación.

### 2.2 Requerimientos

Los requerimientos se obtuvieron del análisis de la operación académica de la facultad y del Reglamento General Académico de la UNAMBA (cursos, grupos paralelos, bloques de una o dos horas por aula, tolerancia de diez minutos, límite de 30 % de inasistencias; Consejo Universitario de la UNAMBA, 2019, arts. 74 y 75) y se formalizaron en 35 requerimientos funcionales (RF-01 a RF-35) agrupados en seis módulos: administración e infraestructura, estudiante y docente, procesamiento de imágenes, lógica de negocio y alertas, nodo IoT y trazabilidad. Se establecieron como restricciones de diseño: ejecución local en CPU, sin servicios de reconocimiento externos, sin entrenamiento de modelos y con un único proceso de servidor.

### 2.3 Diseño de la interfaz y del prototipo

Antes de implementar el panel web se elaboró un prototipo de alta fidelidad en Figma (Figura 1) para validar la navegación y los flujos principales. Cubre inicio de sesión, panel de control, horarios, grupos, docentes, aulas, estudiantes, usuarios, enrolamiento facial, feriados y perfil. Se construyó de forma componentizada (elementos básicos, moléculas, organismos y plantillas de página), organización que se trasladó a Angular, donde cada componente autónomo reutiliza los mismos estilos globales y mantiene una apariencia minimalista y coherente.

> **Figura 1 — imagen que debes subir.** Captura general del tablero de Figma con todas las pantallas del prototipo visibles (vista panorámica, 300 ppp, PNG); si hay espacio, añade como segundo panel la página de componentes (elementos básicos, moléculas y organismos). Título debajo, en negrita y centrado: «**Figura 1** Prototipo de la interfaz del sistema en Figma».

### 2.4 Arquitectura del sistema

El sistema adopta una arquitectura cliente-servidor de monolito modular. El cliente es una aplicación web de una sola página en Angular 21 con componentes autónomos y señales reactivas. El servidor es una API REST en FastAPI (Python 3.13) con acceso asíncrono a PostgreSQL 17 mediante SQLModel. La cámara IP Hikvision de 4 MP, alimentada por PoE+, entrega su flujo principal (canal 101) por RTSP (Schulzrinne et al., 2016); el servidor lo procesa, registra la asistencia y comunica el veredicto al nodo de la puerta por WebSocket (Fette & Melnikov, 2011) y al panel web por eventos enviados por el servidor. La sesión de usuario se gestiona con JSON Web Tokens (Jones et al., 2015) y las contraseñas se almacenan con Argon2 (Biryukov et al., 2021). El acceso se controla por rol (administrador, docente y estudiante) tanto en el cliente como en el servidor. El esquema relacional contiene 18 tablas; los *embeddings* se guardan en una columna `REAL[512]` y la similitud se calcula en NumPy, sin extensiones vectoriales. La Figura 2 muestra la arquitectura general.

> **Figura 2 — imagen que debes subir.** El diagrama `docs/arquitectura-fareas.png` (editable en `docs/arquitectura-fareas.svg`): cámara Hikvision → switch PoE+ → PC servidor (FastAPI + PostgreSQL + modelos ONNX) → router Wi-Fi → nodo ESP32 (anillo LED + zumbador), y el navegador del docente conectado al servidor. Expórtalo a 300 ppp si el texto es pequeño. Título debajo, en negrita y centrado: «**Figura 2** Arquitectura general del sistema».

### 2.5 Canal de reconocimiento facial

El canal de visión se implementó con modelos preentrenados en formato ONNX ejecutados en CPU (onnxruntime), por lo que no se entrenó ningún modelo: el «aprendizaje» del sistema es el enrolamiento de cada estudiante. El procesamiento de cada cuadro comprende:

1. **Detección.** Un detector SCRFD (Guo et al., 2021) con tres niveles de pirámide de características localiza los rostros y estima cinco puntos de referencia (ojos, nariz y comisuras de la boca). La imagen se reescala conservando su proporción (*letterbox*) a 640 × 640 píxeles.
2. **Alineación.** Los cinco puntos se usan para estimar una transformación de similitud hacia la plantilla canónica de 112 × 112 píxeles.
3. **Extracción.** Un modelo ArcFace con *backbone* ResNet-50 entrenado con WebFace600K, subconjunto depurado de WebFace260M (Deng et al., 2022; Zhu et al., 2021), produce un vector de 512 dimensiones normalizado en norma L2.
4. **Identificación.** La similitud entre el vector observado **q** y la plantilla **t** de cada estudiante candidato es el coseno, que al estar normalizados equivale al producto punto:

$$s(\mathbf{q}, \mathbf{t}) = \mathbf{q} \cdot \mathbf{t} \qquad (1)$$

Un rostro se acepta como el estudiante *i* cuando se cumplen simultáneamente tres condiciones:

$$s_i \geq \tau \quad \wedge \quad s_i - \max_{j \neq i} s_j \geq \delta \quad \wedge \quad n_i \geq N \qquad (2)$$

donde τ es el umbral de similitud (0,55, configurable por el administrador), δ es el margen mínimo respecto del segundo mejor candidato de toda la galería (0,06), y *n_i* es el número de cuadros consecutivos en que el mismo estudiante fue el mejor candidato, que debe alcanzar *N* = 3 (equivalente a 1,5 s al procesar 2 cuadros por segundo por aula). Además, solo se analiza el rostro de mayor área y se descartan los rostros cuyo lado menor sea inferior a 60 píxeles. Estas tres condiciones reducen los falsos positivos a costa de una confirmación ligeramente más lenta.

La galería se mantiene en memoria y se recarga al enrolar o eliminar un rostro. La búsqueda se restringe primero a los estudiantes matriculados en el bloque vigente del aula; si el rostro corresponde a un estudiante conocido pero no matriculado en ese bloque, se emite un veredicto de acceso denegado.

### 2.6 Enrolamiento y protección de datos biométricos

Cada estudiante se enrola con tres a cinco fotografías frontales, tomadas con el consentimiento expreso del titular, que es obligatorio y queda registrado con fecha. El sistema rechaza una fotografía que no contiene exactamente un rostro, con rostro menor de 90 píxeles de lado menor, confianza de detección menor a 0,6, giro de cabeza (desviación de la nariz mayor al 35 % de la distancia interocular), inclinación de los ojos mayor a 20° o desenfoque (varianza del laplaciano menor a 25). Con las fotografías aceptadas se calcula un *embedding* por foto, se verifica la consistencia entre fotos (cada una frente al promedio de las demás, similitud mínima de 0,40) y se almacena únicamente el promedio normalizado como plantilla vigente, siguiendo el esquema de plantilla por centroide (Widyani et al., 2026). El sistema rechaza el enrolamiento si la plantilla se parece (≥ 0,60) a la de otra cuenta activa y, en ese caso, nombra la cuenta coincidente. La fotografía de portada se guarda en un almacenamiento privado con URL firmada, y es posible eliminar embeddings y fotografía con una sola operación. Estas medidas aplican el principio de minimización y los derechos de cancelación previstos en la normativa peruana (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024). Toda acción sensible queda en una bitácora de auditoría.

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

donde *t* es la hora de la marca, *t₀* la hora de inicio y *t_f* la hora de fin del bloque. Las marcas son únicas por estudiante y sesión. Al cierre se generan las faltas de los matriculados sin marca. El porcentaje acumulado de inasistencia de un estudiante en un curso se calcula como:

$$P = \frac{F}{S} \times 100 \qquad (4)$$

siendo *F* las faltas no justificadas y *S* las sesiones válidas realizadas (excluidas las canceladas y los feriados). Se envía un aviso preventivo cuando *P* ≥ 20 % y un aviso de inhabilitación cuando *P* > 30 %, una sola vez por nivel y con un mínimo de cuatro sesiones realizadas; ambos umbrales son parámetros que el administrador puede modificar. Los umbrales de 10 minutos y de 30 % provienen del Reglamento General Académico (Consejo Universitario de la UNAMBA, 2019, arts. 74 y 75). Los docentes pueden rectificar estados y registrar justificaciones, con motivo obligatorio y registro en la bitácora.

### 2.8 Señalización en la puerta y monitoreo en vivo

El nodo de la puerta es un ESP32 con un anillo de 16 LED WS2812B y un zumbador activo. Recibe el veredicto por WebSocket y lo muestra con el semáforo del sistema: verde y un pitido (asistió), amarillo y dos pitidos (tardanza), rojo y tono sostenido (acceso denegado) y azul en silencio (sin clase o rostro no identificado).

El panel de monitoreo muestra el video de la cámara con latencia sub-segundo mediante WebRTC (Alvestrand, 2021), servido a través de un repetidor de video local que convierte el flujo RTSP; si no está disponible, el panel recurre a un flujo MJPEG. Un canal de eventos del servidor entrega las coordenadas normalizadas de los rostros detectados, y el cliente dibuja sobre el video un recuadro con esquinas cuyo color corresponde al veredicto vigente. El módulo de importación de horarios, mallas curriculares y nóminas utiliza reconocimiento óptico de caracteres basado en PP-OCR (Li et al., 2022) con una pantalla de revisión antes de guardar.

### 2.9 Procedimiento y plan de evaluación

La evaluación tuvo cuatro componentes alineados con los objetivos: (1) **pruebas automatizadas** de la API (autenticación, catálogo, matrícula, reglas de ventana e inhabilitación, sesiones, justificaciones, seguridad, WebSocket, reportes y visión) y del cliente, ejecutadas contra la base de datos real del entorno de desarrollo; (2) **mediciones de rendimiento** del canal de reconocimiento (detección, extracción de *embedding*, búsqueda y cuadro completo) sobre 40 cuadros con rostro del video de demostración, en un computador de uso general; (3) **verificación de requerimientos**, contrastando cada uno con la funcionalidad y la prueba que lo respalda; y (4) un **piloto con personas** (protocolo), en el que se calculan la tasa de aceptación verdadera (TAR), la tasa de falsa aceptación (FAR) y la tasa de falso rechazo (FRR):

$$\text{FAR} = \frac{FA}{I}, \qquad \text{FRR} = \frac{FR}{G} = 1 - \text{TAR} \qquad (5)$$

donde *FA* son las aceptaciones erróneas de intentos impostores (*I* intentos) y *FR* los rechazos de intentos genuinos (*G* intentos). Además, se mide la usabilidad con la Escala de Usabilidad del Sistema (Lewis, 2018) y los hallazgos se organizan según las características de calidad del producto de ISO/IEC 25010:2023 (International Organization for Standardization & International Electrotechnical Commission [ISO/IEC], 2023).

## 3. Resultados

### 3.1 Cumplimiento de los requerimientos y pruebas automatizadas

Los 35 requerimientos funcionales (RF-01 a RF-35) se implementaron en software y cuentan con respaldo de pruebas automatizadas o de verificación funcional documentada. Se sustituyó el detector YOLO previsto por SCRFD (RF-17 a RF-20), los umbrales de RF-20 y RF-23 se recalibraron (0,55 de similitud; tardanza hasta el fin del bloque) y el nodo IoT (RF-27 a RF-29 y RF-33) se validó con un simulador de WebSocket, por lo que su prueba física y el piloto con estudiantes están pendientes (Sección 3.4).

El sistema comprende 15 635 líneas de Python en el servidor y 15 004 de TypeScript en el cliente, y expone 125 rutas de API sobre 18 tablas. En una sola corrida sobre la versión final se aprobaron 378 de 388 pruebas del servidor (43 archivos; 8 omitidas por requerir una sesión en día laborable y 2 fallidas porque suponen un dispositivo de ejemplo, esp32-lab305, inexistente en la base de datos del entorno) y 144 de 144 del cliente (33 archivos).

### 3.2 Rendimiento del canal de reconocimiento

Los tiempos medidos se presentan en la Tabla 1. El procesamiento completo de un cuadro (detección, alineación, extracción de *embedding* e identificación) tomó una mediana de 440 ms (percentil 95: 508 ms), ajustado a la frecuencia de 2 cuadros por segundo por aula (intervalo de 500 ms). La búsqueda entre 5 000 plantillas, un orden de magnitud superior al de una facultad, tomó una mediana de 1,1 ms, por lo que no fue necesario un índice vectorial especializado.

**Tabla 1**
**Latencias del canal de reconocimiento (40 cuadros, solo CPU)**

| Etapa | Mediana (ms) | Percentil 95 (ms) |
| --- | --- | --- |
| Detección facial (SCRFD) | 207,1 | 242,1 |
| Extracción de *embedding* (ArcFace R50) | 217,7 | 269,2 |
| Búsqueda entre 5 000 plantillas | 1,1 | 1,5 |
| Cuadro completo (detección, extracción y búsqueda) | 439,8 | 508,4 |

*Nota.* Elaboración propia. Equipo: procesador Intel Core de 12.ª generación con 12 hilos lógicos, Windows 11, sin GPU. Cuadros de 720 × 1280 píxeles (video de demostración). «Cuadro completo» repite la detección y la extracción, por lo que no es la suma de las filas anteriores. En corridas previas, con el equipo bajo carga de otros procesos, las latencias aumentaron varias veces (hasta segundos por cuadro); por eso se reportan la mediana y el percentil 95 de una corrida sin carga adicional.

En la integración con la cámara IP real, el sistema registró la cámara como en línea y detectó rostros del flujo en vivo (Figura 3); en una captura de verificación, el rostro detectado midió 106 píxeles con una confianza de 0,82. El video del panel pasó de presentar retraso acumulado (flujo JPEG secuencial) a una reproducción fluida con WebRTC, observación cualitativa cuya latencia de extremo a extremo se medirá en el piloto.

> **Figura 3 — imagen que debes subir.** Captura del panel «Actividad en tiempo real» del dashboard con el video de la cámara, el recuadro de esquinas sobre el rostro y la etiqueta del veredicto (por ejemplo, «Registro correcto» en verde), junto con la tarjeta de la persona reconocida. Usa un voluntario con consentimiento o difumina rostro y nombre. Título debajo: «**Figura 3** Panel de monitoreo en vivo con el recuadro facial y el veredicto».

### 3.3 Defectos detectados durante la validación

La integración con la cámara real permitió detectar y corregir los defectos de la Tabla 2. El más relevante fue la decodificación de los puntos de referencia faciales con el signo de las distancias invertido: en un cuadro de la prueba los ojos quedaban en la ordenada 549, la nariz en 520 y la boca en 497, es decir, con la boca sobre los ojos. Tras la corrección quedaron en 539, 568 y 591, dentro del recuadro del rostro (486 a 619) y en orden anatómico. Con el defecto, la alineación giraba el rostro casi 180°, lo que explicaba que el sistema rechazara fotos frontales por «cabeza inclinada» y que el reconocimiento fuera poco fiable. Se añadió una prueba de regresión que verifica el orden y la inclusión de los cinco puntos en el recuadro sobre el video de demostración.

**Tabla 2**
**Defectos detectados en la validación y su corrección**

| N.° | Defecto | Efecto observado | Corrección | Verificación |
| --- | --- | --- | --- | --- |
| 1 | Signo invertido al decodificar puntos de referencia | Alineación errónea; rechazo de fotos frontales; reconocimiento poco fiable | Suma de distancias al ancla en lugar de resta | Prueba de regresión sobre video real |
| 2 | Deformación del cuadro al reescalar a 640 × 640 | Menor precisión de detección en video 16:9 | Reescalado con proporción (*letterbox*) | Prueba de visión con modelos reales |
| 3 | Umbral configurable ignorado por el reconocimiento | El valor de Parámetros no afectaba al sistema | El bucle de cámaras aplica el umbral de la base de datos | Revisión de código y pruebas del bucle |
| 4 | Decisión con un solo cuadro y sin margen | Riesgo de falsas aceptaciones | Margen δ, confirmación en *N* cuadros y tamaño mínimo (Ecuación 2) | Pruebas unitarias del canal |
| 5 | Retraso acumulado en el video del panel | Imagen cada vez más atrasada | Lectura continua del último cuadro y luego WebRTC | Observación en la cámara real |

*Nota.* Elaboración propia.

### 3.4 Protocolo de piloto y resultados por completar

El piloto aún no se ha ejecutado, por lo que **la precisión del reconocimiento con estudiantes reales no se reporta**. Las Tablas 3 y 4 son plantillas que se completarán con los datos recolectados y se mantienen vacías para no presentar datos inexistentes.

> **Protocolo propuesto.** Una sola prueba, en el horario de un curso de la docente asesora, con los estudiantes voluntarios del grupo (entre 25 y 35 [CONFIRMAR: cantidad final]) y con el equipo instalado temporalmente en el aula. Cada participante se enrola con 3 a 5 fotos y realiza 6 capturas frente a la cámara (3 en condición normal y 3 en condición adversa, como luz lateral o lentes); al menos cinco personas no enroladas realizan 3 capturas cada una para estimar la falsa aceptación. Durante el bloque, el sistema funciona en paralelo al registro manual de la docente, que se toma como verdad de terreno, y al final se aplican la Escala de Usabilidad del Sistema, un cuestionario breve de percepción y una consulta a la docente. Participan solo quienes firman el consentimiento informado, con la autorización de la docente; los datos se analizan con códigos, solo se registran valores de similitud (sin imágenes ni video) y las plantillas faciales se eliminan al terminar. Los resultados se resumen con intervalos de confianza de Wilson al 95 %.

**Tabla 3**
**Desempeño de reconocimiento en el piloto (por completar)**

| Indicador | Valor |
| --- | --- |
| Participantes enrolados | [COMPLETAR] |
| Intentos genuinos (*G*) | [COMPLETAR] |
| Intentos impostores (*I*) | [COMPLETAR] |
| Tasa de aceptación verdadera (TAR) | [COMPLETAR] |
| Tasa de falsa aceptación (FAR) | [COMPLETAR] |
| Tasa de falso rechazo (FRR) | [COMPLETAR] |
| Tiempo medio hasta el veredicto en la puerta (s) | [COMPLETAR] |

*Nota.* Se calculan con la Ecuación 5 con el umbral τ = 0,55 y con otros dos valores de τ para analizar el compromiso entre FAR y FRR.

**Tabla 4**
**Usabilidad y calidad percibida (por completar)**

| Instrumento | Participantes | Resultado |
| --- | --- | --- |
| Escala de Usabilidad del Sistema (docentes) | [COMPLETAR] | [COMPLETAR] |
| Escala de Usabilidad del Sistema (estudiantes) | [COMPLETAR] | [COMPLETAR] |
| Veredictos correctos en la puerta (ESP32 físico) | [COMPLETAR] | [COMPLETAR] |
| Concordancia con la asistencia manual (porcentaje y kappa de Cohen) | [COMPLETAR] | [COMPLETAR] |

*Nota.* Se aplica la Escala de Usabilidad del Sistema (Lewis, 2018).

## 4. Discusión

### 4.1 Interpretación de los resultados

El sistema cumple los requerimientos funcionales y el canal de reconocimiento opera dentro del presupuesto de tiempo: un cuadro completo en CPU (mediana de 440 ms) cabe en el intervalo de 500 ms entre cuadros, aunque con margen estrecho, pues el percentil 95 (508 ms) lo supera ligeramente. Con una sola aula activa el servidor sostiene los 2 cuadros por segundo sin procesador gráfico; para varias aulas habría que reducir la frecuencia o repartir el trabajo entre procesos. La búsqueda entre 5 000 plantillas en 1,1 ms confirma que el producto punto sobre una matriz en memoria basta a la escala de una facultad; los índices aproximados, pensados para miles de millones de vectores (Johnson et al., 2021), solo se justificarían si el sistema creciera varios órdenes de magnitud.

El hallazgo más importante no fue un número de rendimiento sino un defecto de alineación (Tabla 2): en un canal de reconocimiento implementado a mano, un error de preprocesamiento no lanza una excepción sino que degrada la precisión en silencio, y solo se hizo visible al contrastar los puntos con el recuadro del rostro en video real. Por ello, la prueba de regresión geométrica sobre video real es una aportación metodológica: valida que cada etapa produce salidas plausibles y no solo que el programa se ejecuta.

### 4.2 Comparación con estudios previos

A diferencia de los sistemas reportados, centrados en el modelo y su exactitud (Alhanaee et al., 2021; Widyani et al., 2026), este trabajo integra el reconocimiento con las reglas académicas de una universidad peruana: grupos paralelos, bloques por aula, matrícula, tolerancia, cierre automático de sesiones, justificaciones y alertas de inhabilitación. Coincide con Widyani et al. (2026) en usar ArcFace con ResNet-50 y una plantilla promedio por persona, estrategia que los autores asocian con menor almacenamiento y buen desempeño con pocas muestras de enrolamiento. Sus cifras (92,86 % de exactitud y 4,76 % de falsa aceptación) aún no son comparables, porque este manuscrito no incluye el piloto (Tabla 3). Sí lo son las decisiones de diseño: aquí la FAR se controla de forma explícita con el margen δ y la confirmación en varios cuadros (Ecuación 2), que priorizan evitar el registro de una persona equivocada, el error más costoso en este dominio.

### 4.3 Implicaciones

En lo práctico, la solución funciona con equipamiento común de la facultad y sin servicios externos de reconocimiento, lo que reduce costos y mantiene los datos biométricos bajo control institucional; el enrolamiento con validación de calidad y detección de duplicados reduce las fotos deficientes y las cuentas repetidas. En lo normativo, el consentimiento obligatorio, el almacenamiento de plantillas y no de imágenes de cada pasada, la eliminación a solicitud y la bitácora de auditoría se alinean con la protección de datos sensibles (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024). En lo académico, el estudiante ve su porcentaje de inasistencia en tiempo real y el docente cuenta con rectificación auditable.

### 4.4 Limitaciones

Las limitaciones son siete. Primero, la precisión con estudiantes reales no se ha medido: los resultados son evidencia técnica y no de desempeño biométrico. Segundo, el sistema no detecta vida (*liveness*), por lo que una fotografía o una pantalla podría intentar suplantar a un estudiante (Yu et al., 2023). Tercero, el desempeño puede variar entre grupos demográficos (Grother et al., 2019), por lo que el piloto debe desagregar resultados si la muestra lo permite. Cuarto, las latencias se midieron en un solo equipo y con un video de demostración, con alta variabilidad cuando el equipo estaba ocupado, y no con varias aulas simultáneas. Quinto, la prueba física del nodo ESP32 y la latencia de extremo a extremo del video están pendientes. Sexto, el piloto se hace una vez, en un curso y con instalación temporal, por lo que no evalúa el uso sostenido ni la variación entre aulas, y el cuestionario de percepción, de elaboración propia, es exploratorio. Séptimo, el reglamento establece que pasada la tolerancia de diez minutos el estudiante no puede ingresar (Consejo Universitario de la UNAMBA, 2019, art. 75), mientras que el sistema registra el ingreso posterior como tardanza hasta el fin del bloque; esta regla es configurable y debe acordarse con la facultad antes de su uso oficial.

### 4.5 Líneas futuras

Se proponen: (a) ejecutar el piloto de la Sección 3.4 y reportar TAR, FAR y FRR con intervalos de confianza; (b) incorporar detección de vida; (c) evaluar modelos de reconocimiento que adaptan el margen a la calidad de la imagen, como AdaFace, que puede mejorar el desempeño con imágenes de baja calidad (Kim et al., 2022); (d) evaluar el producto con las características de calidad de ISO/IEC 25010:2023; y (e) medir el comportamiento con varias aulas concurrentes.

## 5. Conclusiones

1. Se diseñó e implementó un sistema de asistencia con reconocimiento facial e IoT para la Facultad de Informática de la UNAMBA que cumple los 35 requerimientos funcionales especificados, con reglas académicas de ventana de asistencia, cierre automático, justificaciones y alertas de inhabilitación.
2. El canal de reconocimiento (detección, alineación, extracción e identificación) se ejecuta en CPU en una mediana de 440 ms por cuadro y busca entre 5 000 plantillas en 1,1 ms, lo que permite operar a unos 2 cuadros por segundo en un aula sin procesador gráfico.
3. La validación con la cámara real detectó y permitió corregir un defecto de alineación facial que degradaba el reconocimiento; se incorporó una prueba de regresión y criterios de decisión más estrictos (margen, confirmación y tamaño mínimo).
4. La precisión del reconocimiento con estudiantes reales se determinará con el piloto descrito, cuyo protocolo e indicadores (TAR, FAR y FRR) quedaron definidos.

## Declaración de uso de inteligencia artificial generativa

Se utilizó una herramienta de inteligencia artificial generativa (Claude, de Anthropic) como asistente en la programación del sistema y en la redacción y revisión de este manuscrito. Los autores revisaron, verificaron y asumen la responsabilidad del contenido. **[CONFIRMAR: ajusta esta declaración a las secciones exactas en que la usaste, por ejemplo «Introducción, Metodología y Discusión» y «código del sistema».]**

## Declaración de conflicto de interés

Los autores declaran no tener conflictos de interés. **[CONFIRMAR]**

## Declaración ética

Las pruebas técnicas descritas no involucraron la recolección de datos biométricos de terceros. La prueba con estudiantes se realiza con participación voluntaria, consentimiento informado por escrito de cada estudiante y autorización de la docente del curso, con datos seudonimizados y eliminación de las plantillas faciales al finalizar, conforme a los principios de la Ley N.° 29733 y su reglamento. No se tramitó la aprobación de un comité de ética institucional. **[CONFIRMAR]**

---

## Referencias

Alhanaee, K., Alhammadi, M., Almenhali, N., & Shatnawi, M. (2021). Face recognition smart attendance system using deep transfer learning. *Procedia Computer Science, 192*, 4093–4102. https://doi.org/10.1016/j.procs.2021.09.184

Alvestrand, H. (2021). *Overview: Real-time protocols for browser-based applications* (RFC 8825). Internet Engineering Task Force. https://doi.org/10.17487/RFC8825

Biryukov, A., Dinu, D., Khovratovich, D., & Josefsson, S. (2021). *Argon2 memory-hard function for password hashing and proof-of-work applications* (RFC 9106). Internet Engineering Task Force. https://doi.org/10.17487/RFC9106

Credé, M., Roch, S. G., & Kieszczynka, U. M. (2010). Class attendance in college: A meta-analytic review of the relationship of class attendance with grades and student characteristics. *Review of Educational Research, 80*(2), 272–295. https://doi.org/10.3102/0034654310362998

Consejo Universitario de la Universidad Nacional Micaela Bastidas de Apurímac. (2019, 14 de noviembre). *Reglamento General Académico de la UNAMBA* (Resolución N.° 471-2019-CU-UNAMBA). Universidad Nacional Micaela Bastidas de Apurímac. https://cdn.www.gob.pe/uploads/document/file/8392692/6978325-resolucion-n-471-20219-cu-unamba%282%29.pdf?v=1783351594

Decreto Supremo N.° 016-2024-JUS. (2024, 30 de noviembre). Decreto Supremo que aprueba el Reglamento de la Ley N.° 29733, Ley de Protección de Datos Personales. *El Peruano*. https://www.gob.pe/institucion/anpd/normas-legales/6554453-n-016-2024-jus

Deng, J., Guo, J., Yang, J., Xue, N., Kotsia, I., & Zafeiriou, S. (2022). ArcFace: Additive angular margin loss for deep face recognition. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 44*(10), 5962–5979. https://doi.org/10.1109/TPAMI.2021.3087709

Fette, I., & Melnikov, A. (2011). *The WebSocket protocol* (RFC 6455). Internet Engineering Task Force. https://doi.org/10.17487/RFC6455

Grother, P., Ngan, M., & Hanaoka, K. (2019). *Face recognition vendor test (FRVT) part 3: Demographic effects* (NISTIR 8280). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.IR.8280

Guo, J., Deng, J., Lattas, A., & Zafeiriou, S. (2021). *Sample and computation redistribution for efficient face detection*. arXiv. https://doi.org/10.48550/arXiv.2105.04714

Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). Design science in information systems research. *MIS Quarterly, 28*(1), 75–105. https://doi.org/10.2307/25148625

International Organization for Standardization & International Electrotechnical Commission. (2023). *ISO/IEC 25010:2023. Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Product quality model* (2nd ed.). https://www.iso.org/standard/78176.html

Johnson, J., Douze, M., & Jégou, H. (2021). Billion-scale similarity search with GPUs. *IEEE Transactions on Big Data, 7*(3), 535–547. https://doi.org/10.1109/TBDATA.2019.2921572

Jones, M., Bradley, J., & Sakimura, N. (2015). *JSON Web Token (JWT)* (RFC 7519). Internet Engineering Task Force. https://doi.org/10.17487/RFC7519

Kim, M., Jain, A. K., & Liu, X. (2022). AdaFace: Quality adaptive margin for face recognition. In *2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 18729–18738). IEEE. https://doi.org/10.1109/CVPR52688.2022.01819

Lewis, J. R. (2018). The System Usability Scale: Past, present, and future. *International Journal of Human–Computer Interaction, 34*(7), 577–590. https://doi.org/10.1080/10447318.2018.1455307

Ley N.° 29733. (2011, 3 de julio). Ley de Protección de Datos Personales. *El Peruano*. https://cdn.www.gob.pe/uploads/document/file/272360/Ley%20N%C2%BA%2029733.pdf.pdf?v=1618338779

Li, C., Liu, W., Guo, R., Yin, X., Jiang, K., Du, Y., Du, Y., Zhu, L., Lai, B., Hu, X., Yu, D., & Ma, Y. (2022). *PP-OCRv3: More attempts for the improvement of ultra lightweight OCR system*. arXiv. https://doi.org/10.48550/arXiv.2206.03001

Minaee, S., Luo, P., Lin, Z., & Bowyer, K. (2021). *Going deeper into face detection: A survey*. arXiv. https://doi.org/10.48550/arXiv.2103.14983

Peffers, K., Tuunanen, T., Rothenberger, M. A., & Chatterjee, S. (2007). A design science research methodology for information systems research. *Journal of Management Information Systems, 24*(3), 45–77. https://doi.org/10.2753/MIS0742-1222240302

Schulzrinne, H., Rao, A., Lanphier, R., Westerlund, M., & Stiemerling, M. (2016). *Real-Time Streaming Protocol version 2.0* (RFC 7826). Internet Engineering Task Force. https://doi.org/10.17487/RFC7826

Wang, M., & Deng, W. (2021). Deep face recognition: A survey. *Neurocomputing, 429*, 215–244. https://doi.org/10.1016/j.neucom.2020.10.081

Widyani, S. P., Suroso, S., & Taqwa, A. (2026). Real-time student attendance recognition using a centroid based MTCNN–ArcFace framework. *Edumatic: Jurnal Pendidikan Informatika, 10*(2), 360–369. https://doi.org/10.29408/edumatic.v10i2.35448

Yu, Z., Qin, Y., Li, X., Zhao, C., Lei, Z., & Zhao, G. (2023). Deep learning for face anti-spoofing: A survey. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 45*(5), 5609–5631. https://doi.org/10.1109/TPAMI.2022.3215850

Zhu, Z., Huang, G., Deng, J., Ye, Y., Huang, J., Chen, X., Zhu, J., Yang, T., Lu, J., Du, D., & Zhou, J. (2021). WebFace260M: A benchmark unveiling the power of million-scale deep face recognition. In *2021 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 10487–10497). IEEE. https://doi.org/10.1109/CVPR46437.2021.01035


---

## NOTAS PARA LOS AUTORES (eliminar este bloque antes de enviar)

1. **Formato:** las normas piden el envío en Word (`titulo_corto.docx`) siguiendo la plantilla oficial; este `.md` es el contenido. Al pasarlo a Word, verifica que el manuscrito quede entre 8 y 14 páginas (incluye tablas, figuras y referencias).
2. **Doble ciego:** esta versión no incluye nombres, ORCID, correos, filiaciones, biografías ni agradecimientos. Cuando el artículo sea aceptado, la plantilla pide los datos completos de cada autor, el DOI y las fechas.
3. **FERCYT categoría D:** las bases piden además la constancia de aprobación para publicación del Fondo Editorial, la solicitud de admisión (Anexo 08), la constancia de matrícula del responsable, la constancia de inducción y la carta del asesor (Anexo 09). Recepción del artículo: 5 y 6 de noviembre de 2026, en mesa de partes.
4. **Producto y evidencia:** la categoría D exige artículo + prototipo/software. Prepara la demostración para la sustentación (20 puntos), incluidas las pruebas del nodo ESP32 físico.
5. **Resultados por completar:** Tablas 3 y 4 (piloto), las figuras 1 a 3 y las declaraciones marcadas con [CONFIRMAR]. Enlace de Figma: no se incluye en el manuscrito anónimo porque el archivo público puede mostrar el nombre del propietario; agrégalo cuando el artículo sea aceptado y se soliciten los datos completos: https://www.figma.com/design/G9ThNSqAy3N22tD0YPfJly/Dise%C3%B1o-proyecto Sin el piloto, el criterio «Evaluación y validación» (20 puntos) queda sustentado solo por la evidencia técnica.
6. **Referencias:** las 25 referencias fueron verificadas con Crossref, arXiv, el portal de la revista o el portal oficial gob.pe; 15 de las 25 son de 2021 a 2026 (60 %). Las normas piden mínimo 18 y 50 % de los últimos cinco años. Las RFC y los documentos de arXiv son normas técnicas y preprints; si prefieres solo fuentes en Scopus/Web of Science, sustitúyelos. El Reglamento General Académico de la UNAMBA (Res. 471-2019-CU) se citó a partir de la copia del documento (arts. 74 a 76, p. 18); el enlace público es el del portal gob.pe; falta verificar que los artículos citados no hayan sido modificados (una resolución posterior del Consejo Universitario modificó los arts. 52 y 53, no los citados aquí, pero conviene confirmarlo).
7. **Similitud:** el límite es 25 % sin contar citas y referencias. Revisa el manuscrito con tu software antiplagio antes de enviarlo.
8. **Inteligencia artificial:** las normas exigen declarar el uso de IA generativa y las secciones donde se usó. Ajusta la declaración a la realidad.
9. **Número de autores y contribuciones:** recomendado máximo 6; todos deben haber contribuido sustancialmente y aprobar la versión final.
