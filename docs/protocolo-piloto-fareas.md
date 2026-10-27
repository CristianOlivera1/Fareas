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
| Usabilidad del panel web | SUS respondido por la docente (y por otros docentes si prueban el panel) |
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
5. **Cuestionarios** al terminar la clase: los estudiantes responden solo el cuestionario de percepción (no operan ninguna interfaz); la docente responde el SUS sobre el panel y las tres preguntas de la Sección 6. Quien desarrolla o administra la prueba no responde el SUS, porque su opinión está sesgada.
6. **Cierre.** Descargar el CSV desde la pantalla Prueba piloto, eliminar los rostros enrolados (función de eliminación del sistema) y retirar el equipo. El botón "Borrar datos del piloto" vacía las capturas si hay que repetir el ensayo.

## 4. Análisis

La pantalla Prueba piloto calcula en el momento, con los datos guardados:

- Identificación correcta (TAR), falso rechazo (FRR), identificación como otra persona y falsa aceptación (FAR), cada uno con su intervalo de confianza de 95 % (método de Wilson).
- La curva por cuadro que muestra cómo cambian FAR y FRR al variar el umbral.

Los campos Umbral, Margen y Cuadros recalculan los resultados con otros valores (por ejemplo, 0,50 y 0,60) sin repetir las capturas. Para la concordancia con la asistencia manual, se compara por estudiante el registro del sistema con el de la docente (presente/ausente y asistió/tardanza) y se calcula el porcentaje de coincidencia y el kappa de Cohen. SUS: a los ítems impares se les resta 1, a los pares se les resta su valor de 5, se suma y se multiplica por 2,5 (Lewis, 2018). Percepción: mediana y distribución porcentual por ítem. Con *n* ≈ 30 no se aplican pruebas de hipótesis; se reportan intervalos de confianza y descripciones. Los resultados completan las Tablas 6 y 7 del artículo.
