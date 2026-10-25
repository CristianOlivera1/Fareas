# Guía de la prueba piloto de FAREAS (uso interno)

**Alcance.** Una sola prueba, en el horario de un curso de la docente asesora, con los estudiantes voluntarios del grupo (entre 25 y 35). El equipo se instala temporalmente en el aula y se retira al terminar. El sistema funciona en paralelo al control oficial: la docente sigue pasando su asistencia como siempre, y ese registro es la verdad de terreno. Ningún resultado afecta las notas ni la matrícula.

| Dato | Valor |
| --- | --- |
| Curso, aula y bloque | [COMPLETAR] |
| Fecha de la prueba | [COMPLETAR] |
| Estudiantes que aceptan (*n*) | [COMPLETAR] |

## 1. Qué se mide

| Indicador | Cómo se obtiene |
| --- | --- |
| TAR, FRR e identificación errónea | Capturas de 10 s de cada estudiante enrolado (pantalla Prueba piloto) |
| FAR | Capturas de personas no enroladas |
| Curva FAR–FRR por umbral | Mismos datos, calculada por cuadro |
| Concordancia con la asistencia manual | Hoja de verdad de terreno de la clase (una sesión) |
| Tiempo de enrolamiento y hasta el veredicto | Cronómetro y hoja de registro |
| Usabilidad | SUS (estudiantes y docente) |
| Percepción y privacidad | Cuestionario corto de 6 ítems |

Criterios de referencia (con *n* ≈ 30 se leen con sus intervalos de confianza): TAR ≥ 90 %, 0 identificaciones erróneas, 0 falsas aceptaciones, concordancia con la asistencia manual ≥ 90 %, SUS ≥ 68 y veredicto en la puerta en ≤ 3 s. Como comparación, un sistema con ArcFace y plantilla promedio reportó FAR de 4,76 % y FRR de 2,38 % en una escuela secundaria (Widyani et al., 2026).

Precisión esperada: con 100 intentos sin errores el límite superior del IC 95 % es 3,7 %; con 180 intentos, 2,1 %; con 300, 1,3 %. La prueba permite estimar el orden de magnitud, no demostrar una FAR ≤ 1 %.

## 2. Preparación

- [ ] Autorización de la docente y consentimiento firmado por cada estudiante (Sección 7).
- [ ] Cámara Hikvision en el flujo principal (canal 101, H.264), a la altura del rostro, de frente a la puerta, con luz frontal y sin contraluz.
- [ ] Cámara y nodo ESP32 en línea en el panel de dispositivos; video fluido en el dashboard; go2rtc activo.
- [ ] Horario del aula cargado y hora del servidor correcta.
- [ ] Parámetros anotados: umbral 0,55; margen 0,06; 3 cuadros de confirmación; rostro mínimo 60 px; canal RTSP; versión del sistema.
- [ ] Una captura de prueba en la pantalla Prueba piloto devuelve cuadros con rostro (si devuelve 0, acercar a la persona o mejorar la luz); luego se borran los datos de ensayo.
- [ ] Ensayo con 2 o 3 voluntarios cuyos datos se descartan.
- [ ] Alias asignados (P01, P02…). La tabla alias–estudiante se guarda aparte.

## 3. Procedimiento del día

Todo se hace desde la pantalla **Herramientas → Prueba piloto** del sistema (solo administrador). No hay que escribir comandos: el sistema guarda por sí solo, en cada captura, los valores de similitud de la persona contra todas las plantillas enroladas (sin imágenes ni video).

1. **Enrolamiento** (de 2 a 3 min por estudiante; puede hacerse el día previo o con dos computadores en paralelo), desde Enrolamiento facial, con 3 a 5 fotos frontales. Se anota cuántas fotos se rechazaron y el tiempo.
2. **Capturas controladas** antes de la clase (de 40 a 60 min). En la pantalla Prueba piloto se elige al estudiante y la condición, se pulsa **Capturar** y el estudiante camina hacia la puerta como cuando ingresa; la captura dura 10 s. Por estudiante: 3 capturas **normales** y 3 **adversas** (luz lateral, lentes o distancia distinta). La tabla "Avance por estudiante" marca en verde lo completado y muestra cuántos faltan. Orden aleatorio.
3. **Personas no enroladas** (al menos 5, 3 capturas cada una): se marca la casilla "Persona no enrolada" y se pulsa Capturar.
4. **Clase real.** El sistema funciona en la puerta durante el bloque mientras la docente pasa su lista. Un observador completa la hoja de la Sección 5. Al cierre se exporta la asistencia del sistema (Reportes) para compararla con el registro manual.
5. **Cuestionarios** al terminar la clase: SUS y percepción a los estudiantes; SUS y las tres preguntas de la Sección 6 a la docente.
6. **Cierre.** Descargar el CSV desde la pantalla Prueba piloto, eliminar los rostros enrolados (función de eliminación del sistema) y retirar el equipo. El botón "Borrar datos del piloto" vacía las capturas si hay que repetir el ensayo.

## 4. Análisis

La pantalla Prueba piloto calcula en el momento, con los datos guardados:

- Identificación correcta (TAR), falso rechazo (FRR), identificación como otra persona y falsa aceptación (FAR), cada uno con su intervalo de confianza de 95 % (método de Wilson).
- La curva por cuadro que muestra cómo cambian FAR y FRR al variar el umbral.

Los campos Umbral, Margen y Cuadros recalculan los resultados con otros valores (por ejemplo, 0,50 y 0,60) sin repetir las capturas. Para la concordancia con la asistencia manual, se compara por estudiante el registro del sistema con el de la docente (presente/ausente y asistió/tardanza) y se calcula el porcentaje de coincidencia y el kappa de Cohen. SUS: a los ítems impares se les resta 1, a los pares se les resta su valor de 5, se suma y se multiplica por 2,5 (Lewis, 2018). Percepción: mediana y distribución porcentual por ítem. Con *n* ≈ 30 no se aplican pruebas de hipótesis; se reportan intervalos de confianza y descripciones. Los resultados completan las Tablas 6 y 7 del artículo.

## 5. Hoja de registro de la clase

| Alias | Presente (manual) | Hora real de llegada | Estado del sistema | Color en la puerta | Segundos hasta el veredicto | Incidencia |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

Hoja de enrolamiento: alias, fotos intentadas, fotos rechazadas y causa, tiempo (min).

## 6. Instrumentos

**SUS (10 ítems, escala 1 a 5; 1 = totalmente en desacuerdo, 5 = totalmente de acuerdo).** Versión en español de Sevilla-Gonzalez et al. (2020, Apéndice multimedia 2):

1. Me gustaría usar esta herramienta frecuentemente.
2. Considero que esta herramienta es innecesariamente compleja.
3. Considero que la herramienta es fácil de usar.
4. Considero necesario el apoyo de personal experto para poder utilizar esta herramienta.
5. Considero que las funciones de la herramienta están bien integradas.
6. Considero que la herramienta presenta muchas contradicciones.
7. Imagino que la mayoría de las personas aprenderían a usar esta herramienta rápidamente.
8. Considero que el uso de esta herramienta es tedioso.
9. Me sentí muy confiado al usar la herramienta.
10. Necesité saber bastantes cosas antes de poder empezar a usar esta herramienta.

Instrucción: «Por favor seleccione de cada uno de los enunciados la opción que mejor describa su experiencia con la herramienta electrónica. Un puntaje de 1 significa que usted se encuentra totalmente en desacuerdo con el enunciado, mientras que un puntaje en 5 significa que está totalmente de acuerdo; un puntaje de 3 significaría que usted se encuentra neutral con el enunciado.»

**Percepción y privacidad (estudiantes, escala 1 a 5; elaboración propia, uso exploratorio, sin validación formal).**

1. El registro por reconocimiento facial me pareció más rápido que el pase de lista tradicional.
2. El sistema registró mi asistencia correctamente.
3. Pasar frente a la cámara no interrumpió mi ingreso al aula.
4. Entendí el significado de los colores y sonidos de la puerta.
5. Me sentí informado(a) sobre qué datos de mi rostro se guardan y para qué.
6. Usaría este sistema durante todo el semestre.

Pregunta abierta: ¿qué cambiarías o mejorarías?

**Preguntas a la docente (respuesta breve):**

1. ¿Cómo compara el sistema con su forma habitual de tomar asistencia?
2. ¿Qué situaciones de la clase hicieron que el sistema fallara o generara dudas?
3. ¿Qué cambiaría antes de usarlo oficialmente?

## 7. Consentimiento informado (una hoja)

**Estudio:** evaluación de un sistema de asistencia con reconocimiento facial en un aula de la Facultad de Informática de la UNAMBA.

Entiendo que: (1) se tomarán de 3 a 5 fotos de mi rostro para calcular una plantilla facial, que es un dato personal sensible, y se guardará una fotografía de portada; (2) durante las pruebas solo se registrarán valores de similitud, sin grabar video ni imágenes; (3) los datos se usarán solo para evaluar el sistema y para el artículo, no para calificar ni sancionar, y se analizarán con códigos en lugar de mi nombre; (4) mi plantilla y mi fotografía se eliminarán al terminar la prueba; (5) mi participación es voluntaria, no influye en mis notas y puedo retirarme y pedir que se eliminen mis datos cuando quiera, además de ejercer mis derechos de acceso, rectificación, cancelación y oposición (Ley N.° 29733).

Contacto: [COMPLETAR]

Nombre: ______________________  Código: __________  Firma: ______________  Fecha: ____ / ____ / 2026

## Referencias

Lewis, J. R. (2018). The System Usability Scale: Past, present, and future. *International Journal of Human–Computer Interaction, 34*(7), 577–590. https://doi.org/10.1080/10447318.2018.1455307

Sevilla-Gonzalez, M. D. R., Moreno Loaeza, L., Lazaro-Carrera, L. S., Bourguet Ramirez, B., Vázquez Rodríguez, A., Peralta-Pedrero, M. L., & Almeda-Valdes, P. (2020). Spanish version of the System Usability Scale for the assessment of electronic tools: Development and validation. *JMIR Human Factors, 7*(4), e21161. https://doi.org/10.2196/21161

Widyani, S. P., Suroso, S., & Taqwa, A. (2026). Real-time student attendance recognition using a centroid based MTCNN–ArcFace framework. *Edumatic: Jurnal Pendidikan Informatika, 10*(2), 360–369. https://doi.org/10.29408/edumatic.v10i2.35448
