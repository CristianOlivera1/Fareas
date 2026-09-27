"""Pipeline de visión Fareas (Bloque 5) - sin lógica HTTP.

frame_source → detector (SCRFD) → embedder (ArcFace) → recognizer (coseno)
→ pipeline.process_frame() = veredicto Tabla 8 (lo consume el Bloque 6).

Motivación anti-sobre-ingeniería: pesos preentrenados buffalo_l cargados
directamente con onnxruntime; sin InsightFace, sin GPU, sin Docker.
"""
