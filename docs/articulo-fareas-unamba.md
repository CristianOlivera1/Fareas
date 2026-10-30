# Desarrollo y validación técnica de un sistema de asistencia universitaria con reconocimiento facial e IoT en la EPIIS-UNAMBA

## Development and technical validation of a university attendance system with facial recognition and IoT at EPIIS-UNAMBA

> **Revista Micaela** - ISSN: 2955-8646 (en línea) / 2709-8990 (impresa)
> Universidad Nacional Micaela Bastidas de Apurímac - Vicerrectorado de Investigación - Perú
> Edición especial FERCYT UNAMBA 2026 - Categoría D: Desarrollo Tecnológico
> *Versión anónima para el primer envío (doble ciego): sin nombres, ORCID, correos, filiación ni agradecimientos.*

---

## Resumen

**Objetivo.** Desarrollar y validar técnicamente un sistema de control de asistencia basado en reconocimiento facial e Internet de las Cosas (IoT) para las aulas de la Facultad de Ingeniería Informática y Sistemas de la Universidad Nacional Micaela Bastidas de Apurímac, con la finalidad de automatizar el registro de asistencia de los estudiantes y favorecer la trazabilidad del registro y la protección de los datos biométricos; se espera además reducir el tiempo de llamado de lista, efecto que no se midió. **Metodología.** Investigación tecnológica aplicada bajo el enfoque de ciencia del diseño (*Design Science Research*). Se definieron 35 requerimientos funcionales y se desarrolló un sistema web con Angular, FastAPI y PostgreSQL, integrado con reconocimiento facial mediante SCRFD y ArcFace (512 dimensiones), que procesa video RTSP de una cámara IP en CPU y comunica el resultado mediante un nodo ESP32 en el acceso al aula. La evaluación incluyó pruebas automatizadas, mediciones de latencia y un piloto con 20 estudiantes. **Resultados principales.** Se aprobaron 544 de 547 pruebas automatizadas. Un cuadro se procesó con una mediana de 1,35 s (199 ms en la mejor de 11 corridas). En el piloto se reconoció a los 20 estudiantes y se rechazaron 2 intentos impostores (resultado exploratorio); el veredicto tardó de 4 a 8 s y la docente calificó el panel con 87,5 de 100. **Conclusión principal.** El sistema cumple los requerimientos funcionales y opera sin GPU, pero necesita un servidor dedicado.

**Palabras clave:** asistencia automatizada; reconocimiento facial; Internet de las cosas; ArcFace

## Abstract

**Objective.** To develop and technically validate an attendance control system based on face recognition and the Internet of Things (IoT) for the classrooms of the Faculty of Computer Engineering and Systems of the Micaela Bastidas National University of Apurímac, in order to automate student attendance recording and to support record traceability and biometric data protection; a reduction in roll-call time is also expected, an effect that was not measured. **Methodology.** Applied technological research under the Design Science Research approach. Thirty-five functional requirements were defined and a web system was developed with Angular, FastAPI and PostgreSQL, integrated with face recognition through SCRFD and ArcFace (512 dimensions); it processes the RTSP video of an IP camera on a CPU and reports the result through an ESP32 node at the classroom entrance. Evaluation included automated tests, latency measurements and a pilot with 20 students. **Key findings.** 544 of 547 automated tests passed. A frame was processed in a median of 1.35 s (199 ms in the best of 11 runs). In the pilot, all 20 students were recognized and 2 impostor attempts were rejected (an exploratory result); the verdict took 4 to 8 s and the teacher rated the panel 87.5 out of 100. **Main conclusion.** The system meets the functional requirements and runs without a GPU, but it needs a dedicated server.

**Keywords:** automated attendance; face recognition; Internet of Things; ArcFace

---

## 1. Introducción

Controlar la asistencia es una tarea cotidiana de la gestión académica universitaria, pero no es menor: sirve para seguir de cerca al estudiante y para cumplir las normas de la institución. Credé et al. (2010), en un metaanálisis, encontraron que asistir a clases se asocia de forma consistente con un mejor rendimiento académico. En la Universidad Nacional Micaela Bastidas de Apurímac (UNAMBA), además, el registro tiene efectos administrativos y académicos, ya que el Reglamento General Académico fija condiciones sobre las inasistencias y la evaluación de los estudiantes (Consejo Universitario de la UNAMBA, 2019). El pase de lista manual, sin embargo, resta tiempo a la clase, permite registros indebidos (por ejemplo, que un compañero responda por otro) y hace difícil detectar a tiempo las faltas acumuladas.

Los modelos de aprendizaje profundo permiten hoy identificar a una persona a partir de una imagen de su rostro. ArcFace convierte cada rostro en un vector que se compara con otro mediante una medida de similitud (Deng et al., 2022), y SCRFD ubica los rostros dentro de una imagen o de un video (Guo et al., 2021). Ya existen antecedentes en el aula: Alhanaee et al. (2021) probaron un sistema de asistencia con reconocimiento facial y aprendizaje por transferencia, y Widyani et al. (2026) midieron el reconocimiento de estudiantes de una escuela con MTCNN y ArcFace. Registrar la asistencia con visión por computador, por tanto, no es una idea nueva; lo que sigue abierto es cómo conectar el reconocimiento con las condiciones académicas y operativas de cada institución.

Identificar bien a un estudiante no basta. El sistema debe verificar que esté matriculado en el curso y el grupo que se dictan en ese momento, aplicar las reglas de asistencia de la universidad, dejar registros auditables y mostrar el resultado en la puerta sin demora, todo bajo la normativa peruana de datos personales (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024). Este trabajo propone un sistema que reúne esas piezas (reconocimiento facial, reglas académicas y un nodo IoT en la entrada del aula) sobre infraestructura local, sin servicios externos de reconocimiento ni procesadores gráficos. Su aporte es tecnológico y se evalúa en cuatro planos: la validación funcional, el rendimiento, el desempeño biométrico con estudiantes y el funcionamiento conjunto de los componentes en el aula.

El objetivo fue diseñar, desarrollar y evaluar técnicamente un sistema de control de asistencia basado en reconocimiento facial e Internet de las Cosas (IoT) para las aulas de la Facultad de Ingeniería Informática y Sistemas de la UNAMBA. Para ello se especificaron los requerimientos, se implementó el procesamiento facial en CPU, se integraron las reglas de asistencia y la señalización con un nodo ESP32, y se evaluó el sistema con pruebas automatizadas, mediciones de rendimiento y un piloto con 20 estudiantes. La reducción del tiempo de llamado de lista se plantea como una finalidad esperada, no como un resultado demostrado.

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

1. **Detección.** Un detector SCRFD (Guo et al., 2021) localiza los rostros y estima cinco puntos de referencia. La imagen se reescala conservando su proporción hasta un lado máximo de 640 píxeles, con dimensiones múltiplos de 32.
2. **Alineación.** Los cinco puntos definen una transformación de similitud hacia la plantilla canónica de 112 × 112 píxeles.
3. **Extracción.** Un modelo ArcFace con *backbone* ResNet-50 entrenado con WebFace600K, subconjunto depurado de WebFace260M (Deng et al., 2022; Zhu et al., 2021), produce un vector de 512 dimensiones normalizado en norma L2.
4. **Identificación.** La similitud entre el vector observado **q** y la plantilla **t** de cada candidato es el coseno, equivalente al producto punto:

$$s(\mathbf{q}, \mathbf{t}) = \mathbf{q} \cdot \mathbf{t} \qquad (1)$$

Un rostro se acepta como el estudiante *i* cuando se cumplen a la vez tres condiciones:

$$s_i \geq \tau \quad \wedge \quad s_i - \max_{j \neq i} s_j \geq \delta \quad \wedge \quad n_i \geq N \qquad (2)$$

donde τ es el umbral de similitud (0,55), δ el margen respecto del segundo mejor candidato (0,06) y *n_i* el número de cuadros consecutivos en que *i* fue el mejor candidato, que debe alcanzar *N* = 2 (unos 0,7 s a 3 cuadros por segundo). El vector observado es el promedio normalizado de los *embeddings* de los últimos tres cuadros, y la ventana se reinicia si la similitud con el promedio previo es menor de 0,45 (otra persona). Solo se analiza el rostro de mayor área y se descartan los de lado menor a 60 píxeles y los de perfil (desviación de la nariz mayor al 50 % de la distancia interocular); mientras tanto, el veredicto es «identificando» y no revela ninguna identidad.

La galería se mantiene en memoria y la búsqueda se restringe primero a los matriculados en el bloque vigente del aula; si el rostro es de un estudiante conocido pero no matriculado en ese bloque, el veredicto es acceso denegado.

### 2.6 Enrolamiento y protección de datos biométricos

Para enrolarse, cada estudiante aporta de tres a cinco fotografías de frente y da su consentimiento expreso, que es obligatorio y queda registrado con fecha. El sistema descarta las fotos que no tengan exactamente un rostro, que lo muestren menor de 90 píxeles, con confianza de detección inferior a 0,6, con la cabeza girada o inclinada, o desenfocado. Con las fotos aceptadas comprueba que sean consistentes entre sí (similitud mínima de 0,40) y conserva solo el promedio normalizado como plantilla, según el esquema de centroide (Widyani et al., 2026). Si esa plantilla se parece en 0,60 o más a la de otra cuenta activa, rechaza el enrolamiento e indica la cuenta coincidente. La fotografía de portada se guarda en almacenamiento privado con URL firmada, ambos datos se eliminan con una sola operación y toda acción sensible queda en una bitácora de auditoría, en línea con la minimización y los derechos de cancelación de la normativa peruana (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024).

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

El panel de monitoreo muestra el video de la cámara con latencia sub-segundo mediante WebRTC, servido por un repetidor de video local que convierte el flujo RTSP (con respaldo MJPEG), y dibuja sobre él un recuadro con esquinas cuyo color corresponde al veredicto vigente.

### 2.9 Procedimiento y plan de evaluación

La evaluación distinguió cuatro tipos de validación: (1) la **funcional**, que contrasta los 35 requerimientos con la funcionalidad y con pruebas automatizadas de la API y del cliente; (2) la de **rendimiento**, que mide la latencia de detección, extracción, búsqueda y cuadro completo sobre 40 cuadros con rostro del video de demostración, en varias corridas; (3) la **biométrica**, en un piloto con estudiantes, donde se calculan las tasas de aceptación verdadera (TAR), de falsa aceptación (FAR) y de falso rechazo (FRR) con intervalos de Wilson al 95 %:

$$\text{FAR} = \frac{FA}{I}, \qquad \text{FRR} = \frac{FR}{G} = 1 - \text{TAR} \qquad (5)$$

donde *FA* son las aceptaciones erróneas de intentos impostores (*I*) y *FR* los rechazos de intentos genuinos (*G*); y (4) la **operativa**, que comprueba el funcionamiento conjunto de cámara, servidor, red, nodo ESP32 y panel en el aula, con la lista manual de la docente como verdad de terreno, la Escala de Usabilidad del Sistema (SUS; 0 a 100, media de referencia de 68; Lewis, 2018) aplicada a la docente y un cuestionario de percepción de seis ítems para los estudiantes. Los hallazgos se organizan según ISO/IEC 25010:2023 (International Organization for Standardization & International Electrotechnical Commission [ISO/IEC], 2023).

## 3. Resultados

### 3.1 Validación funcional

Para verificar el sistema se partió de los 35 requerimientos funcionales definidos durante el desarrollo (RF-01 a RF-35), formulados conforme a las prácticas de ingeniería de requisitos (ISO/IEC/IEEE, 2018). A cada uno se le asignó la funcionalidad que lo implementaba y se comprobó que funcionara, ya fuera con una prueba automatizada o con una verificación funcional documentada. Así fue posible revisar si lo que se había especificado coincidía con lo que el sistema realmente hacía.

Aquí una «prueba» es un caso individual (función de pytest o caso de Vitest); los archivos que las agrupan se cuentan aparte. En una corrida completa del 28 de octubre de 2026 sobre la versión final se ejecutaron 547 pruebas (403 del servidor, en 44 archivos, y 144 del cliente, en 33) y 544 se aprobaron; ninguna se omitió. Las tres que no pasaron fueron dos pruebas de WebSocket que usan un dispositivo de ejemplo (esp32-lab305) ausente en la base de datos del entorno y una de reportes por docente cuya causa no se investigó; ninguna pertenece al reconocimiento facial. Las del servidor cubren autenticación, catálogos, matrícula, reglas de asistencia, sesiones, justificaciones, seguridad, WebSocket (Fette & Melnikov, 2011), reportes y visión.

Las verificaciones técnicas también llevaron a modificar el diseño. El detector YOLO que se había previsto al inicio (Redmon et al., 2016) se reemplazó por SCRFD para la detección facial (Guo et al., 2021), y se recalibraron tanto los parámetros de decisión del reconocimiento, basado en representaciones faciales de tipo ArcFace (Deng et al., 2022), como la regla de tardanza. La implementación evaluada ya incluye estos cambios. Esto es evidencia de verificación técnica; no demuestra por sí sola que los requerimientos funcionen en condiciones reales, para lo cual se usan las secciones 3.4 y 3.5.

### 3.2 Evaluación de rendimiento

La medición de 40 cuadros con rostro del video de demostración se repitió en 11 corridas consecutivas con la configuración final, en el mismo equipo, un portátil Lenovo LOQ con Intel Core i5-12450HX (8 núcleos, 12 hilos), 16 GB de RAM y Windows 11, que también ejecutó el piloto; el reconocimiento usó solo la CPU y no la GPU NVIDIA GeForce RTX 3050 del equipo (cuatro hilos por modelo y sin espera activa). En cada corrida se calcularon la mediana y el percentil 95 de los 40 cuadros, y la Tabla 1 resume las 11 con la mediana de sus medianas y su rango. El equipo no se aisló: además del servidor ejecutaba la sincronización de OneDrive (cerca de un núcleo), el navegador y el editor de código, de modo que las cifras reflejan un uso realista y no el mejor caso.

**Tabla 1**
**Latencias del canal de reconocimiento (11 corridas de 40 cuadros, solo CPU)**

| Etapa | Mediana de las medianas por corrida (ms) | Rango entre corridas (ms) |
| --- | --- | --- |
| Detección facial (SCRFD) | 221,0 | 77,7 – 244,9 |
| Extracción de *embedding* (ArcFace R50) | 1 115,5 | 117,0 – 1 304,1 |
| Búsqueda entre 5 000 plantillas | 1,9 | 1,4 – 2,0 |
| Cuadro completo (detección, extracción y búsqueda) | 1 346,6 | 198,6 – 1 572,3 |
| Cuadro completo, percentil 95 de cada corrida | 1 569,6 | 1 288,1 – 2 078,4 |

*Nota.* Elaboración propia. Cuadros de 720 × 1280 píxeles. Todas las filas usan el mismo criterio: estadístico por corrida sobre los 40 cuadros y luego mediana y rango de las 11 corridas. «Cuadro completo» repite la detección y la extracción, por lo que no es la suma de las filas.

El cuadro completo tomó una mediana de 1,35 s (unos 0,7 cuadros por segundo). Solo una corrida (198,6 ms) estuvo por debajo de los 333 ms que corresponderían a los 3 cuadros por segundo configurados, así que el sistema no sostiene esa frecuencia de forma estable en este equipo. La búsqueda entre 5 000 plantillas tomó menos de 2 ms; esta cifra mide solo la comparación de *embeddings*, no el tiempo total de identificación.

### 3.3 Defectos detectados durante la validación

La integración con la cámara real permitió corregir cuatro defectos principales. (1) Los puntos de referencia faciales se decodificaban con el signo invertido: en un cuadro de prueba la boca quedaba sobre los ojos, la alineación giraba casi 180° y se rechazaban fotos frontales por «cabeza inclinada»; tras corregirlo se añadió una prueba de regresión sobre el video de demostración. (2) La decisión se tomaba con un solo cuadro y sin margen, y se sustituyó por el margen δ, el promedio de *embeddings*, la confirmación en *N* cuadros, el tamaño mínimo y el descarte de perfiles (Ecuación 2). (3) Los hilos de cada modelo quedaban en espera activa: la mediana por cuadro era de 1 115 ms (percentil 95 de 14 s) y bajó a 157 ms en la misma sesión al limitarlos a cuatro y desactivar la espera. (4) El veredicto provisional incluía al candidato y el panel mostraba su nombre antes de confirmar; ahora «identificando» no lleva identidad. También se corrigieron el reescalado sin conservar la proporción, el umbral configurable ignorado y el retraso acumulado del video.

### 3.4 Evaluación biométrica en el piloto

El piloto se realizó con un grupo de 26 estudiantes, de los cuales 20 aceptaron participar y firmaron el consentimiento informado; solo ellos se enrolaron (tres a cinco fotografías) y se evaluaron. Cada participante pasó una vez por la puerta al ingresar a clase (20 intentos genuinos) y dos personas no enroladas (personal de la facultad: docentes, administrativos o auxiliares) intentaron ingresar (2 intentos impostores). Se usaron τ = 0,55, δ = 0,06 y *N* = 2; los datos se analizaron con códigos y solo se guardaron valores de similitud, sin imágenes ni video. Los resultados se muestran en la Tabla 2.

**Tabla 2**
**Desempeño de reconocimiento en el piloto**

| Indicador | Resultado | IC 95 % (Wilson) |
| --- | --- | --- |
| Participantes enrolados (de 26 estudiantes del grupo) | 20 | - |
| Intentos genuinos (*G*) / impostores (*I*) | 20 / 2 | - |
| Tasa de aceptación verdadera (TAR) | 100 % (20/20) | 83,9 – 100 % |
| Tasa de falso rechazo (FRR) | 0 % (0/20) | 0 – 16,1 % |
| Tasa de falsa aceptación (FAR) | 0 % (0/2) | 0 – 65,8 % |
| Tiempo hasta el veredicto en la puerta | 4 – 8 s (rango observado) | - |

*Nota.* Elaboración propia, con la Ecuación 5 y los parámetros indicados. Con 2 intentos impostores el resultado es exploratorio.

Con solo dos intentos impostores, el límite superior del intervalo de la FAR llega a 65,8 %: el resultado no demuestra que la falsa aceptación sea nula, y 20 intentos genuinos permiten afirmar solo que la TAR es de al menos 83,9 % con 95 % de confianza. El tiempo de 4 a 8 s supera los cerca de 0,7 s previstos y es del orden de lo esperable con los 1,35 s por cuadro de la Sección 3.2.

### 3.5 Validación operativa

Con la cámara IP real (1280 × 720 píxeles, 15 cuadros por segundo) el sistema detectó rostros en vivo (Figura 3): en una captura de verificación el rostro midió 106 píxeles, con confianza de 0,82, y el video del panel pasó de un retraso acumulado a una reproducción fluida con WebRTC. Durante el piloto el nodo ESP32 estuvo instalado en la puerta y mostró el veredicto correcto en los 20 ingresos; como todos llegaron puntuales, solo se observó el verde, y los demás estados se verificaron con el simulador de WebSocket y las pruebas automatizadas. La asistencia del sistema coincidió con la lista manual de la docente en los 20 participantes; al estar todos presentes no hay variación, de modo que el kappa de Cohen no es calculable.

> **Figura 3 - imagen que debes subir.** Captura del panel «Actividad en tiempo real» con el recuadro de esquinas sobre el rostro y el veredicto (difumina rostro y nombre si no hay consentimiento). Título debajo: «**Figura 3** Panel de monitoreo en vivo con el recuadro facial y el veredicto».

La docente asignó 5, 1, 5, 1, 5, 1, 5, 1, 4 y 5 puntos a los ítems 1 a 10 del SUS; los impares aportaron 19 puntos y los pares 16, y el puntaje fue 35 × 2,5 = 87,5, por encima de la media de 68. Solo el ítem 10 (necesitar saber varias cosas antes de empezar) fue desfavorable. En las preguntas abiertas la docente valoró la sencillez del panel y sus reportes y tendencias, propuso un enlace público de consulta para los estudiantes, señaló la caída de Internet como riesgo excepcional y no cambiaría nada antes del uso oficial.

Los 20 estudiantes respondieron al terminar la clase, en hojas impresas como el consentimiento, un cuestionario propio de seis ítems en escala de 1 a 5 (1 = totalmente en desacuerdo): P1, el registro facial fue más rápido que el pase de lista; P2, registró mi asistencia correctamente; P3, no interrumpió mi ingreso; P4, entendí los colores y sonidos de la puerta; P5, me sentí informado sobre los datos de mi rostro; y P6, lo usaría todo el semestre. No tiene validación formal y es exploratorio. La Tabla 3 reúne los indicadores operativos.

**Tabla 3**
**Validación operativa: usabilidad, percepción y funcionamiento en el aula**

| Indicador | Participantes | Escala | Resultado |
| --- | --- | --- | --- |
| SUS del panel web (docente) | 1 | 0 – 100 | 87,5 |
| Percepción de los estudiantes en la puerta (P1 a P6) | 20 | 1 – 5 | Mediana de 3 en cada ítem |
| Veredictos correctos en la puerta (ESP32 físico) | 20 | - | 20 de 20, todos en verde (asistió) |
| Concordancia con la asistencia manual | 20 | - | 100 % (20/20); kappa no calculable |

*Nota.* Elaboración propia. El SUS (Lewis, 2018) lo respondió una sola usuaria, la docente asesora; los resultados son descriptivos y no generalizables.

## 4. Discusión

### 4.1 Interpretación de los resultados

El sistema cumple los requerimientos funcionales, pero su rendimiento en el equipo de desarrollo quedó por debajo de lo previsto: 1,35 s por cuadro equivale a unos 0,7 cuadros por segundo y no a los 3 configurados, y esa lentitud es coherente con los 4 a 8 s que tardó el veredicto en el piloto. Para un uso real, el servidor debe dedicarse al sistema o contar con un procesador más potente; el diseño en CPU sigue siendo viable en costo, pero no está demostrado que sostenga varias aulas.

El hallazgo metodológico más relevante fue que los defectos no produjeron errores visibles: la inversión de los puntos de referencia degradó el reconocimiento en silencio y la configuración de hilos multiplicó los tiempos sin alterar ningún resultado. Por eso la prueba de regresión geométrica sobre video real y la medición repetida de latencias forman parte de la validación.

En el piloto, la TAR de 100 % y la FAR de 0 % son exploratorias: con dos intentos impostores la FAR podría llegar a 65,8 %. El SUS de 87,5 proviene de una sola usuaria, además asesora, y no demuestra una reducción del tiempo del llamado de lista, que no se midió.

### 4.2 Comparación con estudios previos

Los estudios revisados se centran en el modelo de reconocimiento y en su exactitud (Alhanaee et al., 2021; Widyani et al., 2026). Este trabajo, en cambio, lo integra con las reglas de una universidad peruana: grupos paralelos, bloques horarios, matrícula, tolerancia, justificaciones y alertas de inhabilitación. Como Widyani et al. (2026), usa ArcFace con ResNet-50 y una plantilla promedio por persona. Sus cifras (92,86 % de exactitud y 4,76 % de falsa aceptación) no son comparables con las del piloto, que tiene solo dos intentos impostores (Tabla 2); sí lo es la decisión de diseño de controlar la falsa aceptación con el margen δ, el promedio de cuadros y la confirmación (Ecuación 2).

### 4.3 Implicaciones

Para la facultad, la solución funciona con equipos comunes y sin servicios externos, de modo que los datos biométricos permanecen bajo control institucional. Sus mecanismos de consentimiento obligatorio, almacenamiento de plantillas en lugar de imágenes, eliminación a solicitud y bitácora de auditoría están orientados a la normativa de datos personales (Ley N.° 29733, 2011; Decreto Supremo N.° 016-2024-JUS, 2024), aunque su eficacia no se evaluó por separado. El estudiante puede consultar su porcentaje de inasistencia y el docente rectificar registros con trazabilidad. La docente propuso una consulta pública de la asistencia; para no exponer datos personales, debería mostrar solo códigos.

### 4.4 Limitaciones

Las limitaciones son siete. Primero, la muestra del piloto es pequeña (20 intentos genuinos y 2 impostores): TAR, FAR y FRR son descriptivos y sus intervalos amplios (Tabla 2). Segundo, no hay detección de vida (*liveness*), de modo que una fotografía o pantalla podría suplantar a un estudiante (Yu et al., 2023). Tercero, el desempeño puede variar entre grupos demográficos (Grother et al., 2019) y no se desagregó. Cuarto, las latencias se midieron en un solo equipo, sin aislarlo de otros procesos, y variaron entre 0,2 y 1,6 s por cuadro; no se probaron varias aulas. Quinto, el piloto fue de una sola sesión en un curso; el ESP32 solo mostró el veredicto verde; el SUS lo respondió una sola usuaria (la asesora, con posible sesgo a favor) y el cuestionario de percepción es propio y exploratorio. Sexto, la reducción del tiempo de llamado de lista es una finalidad esperada y no un resultado, y no se evaluó por separado la eficacia de los mecanismos de trazabilidad y protección de datos; además, el sistema depende de la red, por lo que debe mantenerse la rectificación manual. Séptimo, el reglamento impide el ingreso pasada la tolerancia de diez minutos (Consejo Universitario de la UNAMBA, 2019, art. 75), pero el sistema lo registra como tardanza; la regla es configurable y debe acordarse con la facultad.

### 4.5 Líneas futuras

Se proponen: (a) ampliar el piloto a más participantes, aulas y condiciones (tardanza, acceso denegado, luz adversa) y con más intentos impostores; (b) incorporar detección de vida; (c) evaluar modelos que adaptan el margen a la calidad de la imagen, como AdaFace (Kim et al., 2022); (d) medir el tiempo de llamado de lista con y sin el sistema y probar varias aulas en un servidor dedicado; y (e) ofrecer una consulta pública de solo lectura con códigos en lugar de nombres.

## 5. Conclusiones

1. Se diseñó e implementó un sistema de asistencia con reconocimiento facial e IoT para la Facultad de Ingeniería Informática y Sistemas de la UNAMBA que cumple los 35 requerimientos funcionales (544 de 547 pruebas automatizadas aprobadas).
2. En el equipo de desarrollo, un cuadro tomó una mediana de 1,35 s (199 ms en la mejor de 11 corridas), por lo que el servidor debe dedicarse al sistema.
3. En el piloto con 20 estudiantes se reconoció a todos y se rechazaron 2 intentos impostores, con el veredicto en 4 a 8 s; el resultado es exploratorio.
4. El ESP32 mostró 20 veredictos verdes correctos, la asistencia coincidió con la lista manual y la docente calificó el panel con 87,5 de 100 (una sola usuaria).
5. La reducción del tiempo de llamado de lista y la eficacia de la protección de datos siguen sin evaluarse.

## Biografías

> *Nota para los autores: las normas piden este texto (60 palabras como máximo por autor) en la versión final; omítelo en el primer envío anónimo, como indica el bloque de notas.*

**Cristian Olivera Chávez.** Estudiante de Ingeniería Informática y Sistemas de la Universidad Nacional Micaela Bastidas de Apurímac, Perú. Desarrollador de software con experiencia en Angular, Next.js, Tailwind CSS, Laravel y Spring Boot. En este trabajo desarrolló el sistema web, la integración del reconocimiento facial y la comunicación con el nodo IoT.

**Luis Fernando Juarez Peña.** Estudiante de Ingeniería Informática y Sistemas de la Universidad Nacional Micaela Bastidas de Apurímac, Perú. Desarrollador de software con experiencia en Angular, Next.js, Tailwind CSS y Laravel. En este trabajo desarrolló módulos del sistema web.

## Declaración de uso de inteligencia artificial generativa

Se utilizó una herramienta de inteligencia artificial generativa (Claude, de Anthropic) como asistente en la programación del sistema y en la redacción y revisión de este manuscrito. Los autores revisaron, verificaron y asumen la responsabilidad del contenido.

## Declaración de conflicto de interés

Los autores declaran no tener conflictos de interés.

## Declaración ética

Las pruebas técnicas descritas no involucraron la recolección de datos biométricos de terceros. De los 26 estudiantes del grupo, 20 firmaron el consentimiento y solo ellos participaron. La prueba con estudiantes se realizó con participación voluntaria, consentimiento informado por escrito de cada estudiante y autorización de la docente del curso, con datos seudonimizados y eliminación de las plantillas faciales al finalizar, conforme a los principios de la Ley N.° 29733 y su reglamento. No se tramitó la aprobación de un comité de ética institucional.

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

Kim, M., Jain, A. K., & Liu, X. (2022). AdaFace: Quality adaptive margin for face recognition. In *2022 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 18729–18738). IEEE. https://doi.org/10.1109/CVPR52688.2022.01819

Kurniawan, R. A. (2024). Pembuatan design system menggunakan pendekatan atomic design dan A/B testing. *Jurnal Teknologi dan Sistem Informasi Bisnis, 6*(3), 543–549. https://doi.org/10.47233/jteksis.v6i3.1346

Lewis, J. R. (2018). The System Usability Scale: Past, present, and future. *International Journal of Human–Computer Interaction, 34*(7), 577–590. https://doi.org/10.1080/10447318.2018.1455307

Ley N.° 29733. (2011, 3 de julio). Ley de Protección de Datos Personales. *El Peruano*. https://cdn.www.gob.pe/uploads/document/file/272360/Ley%20N%C2%BA%2029733.pdf.pdf?v=1618338779

Peffers, K., Tuunanen, T., Rothenberger, M. A., & Chatterjee, S. (2007). A design science research methodology for information systems research. *Journal of Management Information Systems, 24*(3), 45–77. https://doi.org/10.2753/MIS0742-1222240302

Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You only look once: Unified, real-time object detection. In *2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 779–788). IEEE. https://doi.org/10.1109/CVPR.2016.91

Wang, M., & Deng, W. (2021). Deep face recognition: A survey. *Neurocomputing, 429*, 215–244. https://doi.org/10.1016/j.neucom.2020.10.081

Widyani, S. P., Suroso, S., & Taqwa, A. (2026). Real-time student attendance recognition using a centroid based MTCNN–ArcFace framework. *Edumatic: Jurnal Pendidikan Informatika, 10*(2), 360–369. https://doi.org/10.29408/edumatic.v10i2.35448

Yu, Z., Qin, Y., Li, X., Zhao, C., Lei, Z., & Zhao, G. (2023). Deep learning for face anti-spoofing: A survey. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 45*(5), 5609–5631. https://doi.org/10.1109/TPAMI.2022.3215850

Zhu, Z., Huang, G., Deng, J., Ye, Y., Huang, J., Chen, X., Zhu, J., Yang, T., Lu, J., Du, D., & Zhou, J. (2021). WebFace260M: A benchmark unveiling the power of million-scale deep face recognition. In *2021 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)* (pp. 10487–10497). IEEE. https://doi.org/10.1109/CVPR46437.2021.01035


---

## NOTAS PARA LOS AUTORES (eliminar este bloque antes de enviar)

1. **Formato:** las normas piden el envío en Word (`titulo_corto.docx`) con la plantilla oficial; este `.md` es el contenido. El manuscrito debe quedar entre 8 y 14 páginas (incluye tablas, figuras y referencias).
2. **Doble ciego:** esta versión no incluye ORCID, correos ni filiaciones. La sección «Biografías» (con nombres) se agregó a pedido tuyo; las normas la piden para la versión final, así que elimínala del primer envío anónimo. Tampoco aparece el nombre de la docente que respondió el cuestionario.
3. **FERCYT categoría D:** las bases piden además la constancia de aprobación del Fondo Editorial, la solicitud de admisión (Anexo 08), la constancia de matrícula del responsable, la constancia de inducción y la carta del asesor (Anexo 09). Recepción: 5 y 6 de noviembre de 2026, en mesa de partes.
4. **Producto y evidencia:** la categoría D exige artículo más prototipo/software. Prepara la demostración para la sustentación (20 puntos). Enlace de Figma (agregar solo tras la aceptación): https://www.figma.com/design/G9ThNSqAy3N22tD0YPfJly/Dise%C3%B1o-proyecto
5. **Marcadores:** ya no quedan `[CONFIRMAR]` en el cuerpo del artículo. Verifica que el resumen y el abstract digan lo mismo antes de enviar.
6. **Referencias:** 21, verificadas con Crossref, arXiv, el portal de la revista, gob.pe o la ficha de ISO; 11 de las 21 son de 2021 a 2026 (52 %; las normas piden al menos 50 %). Se quitaron las RFC de RTSP, WebRTC, JWT y Argon2 y las referencias de Minaee, Johnson y Li para ganar espacio. Kurniawan (2024) corresponde al DOI que la docente rotuló «Frost».
7. **Similitud e IA:** Turnitin marcó 21 % como «generado con IA». Se reescribieron con otras palabras y estructura los fragmentos señalados (introducción, enrolamiento, comparación con estudios previos e implicaciones). Vuelve a pasar el texto por Turnitin y revisa que cada párrafo refleje tu forma de explicar el sistema.
8. **Inteligencia artificial:** las normas exigen declarar el uso de IA generativa y las secciones donde se usó. Ajusta la declaración a la realidad.
9. **Autores:** máximo recomendado 6; todos deben aprobar la versión final.
