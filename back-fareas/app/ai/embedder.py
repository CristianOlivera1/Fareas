"""Embedder ArcFace (models/w600k_r50.onnx) → vector de 512 dimensiones.

Entrada: el frame COMPLETO + los 5 landmarks del detector (SCRFD); aquí se
recorta y se ALINEA el rostro con la similitud transform estándar de
insightface (destino arcface112), que es cómo se generaron los embeddings
del modelo: sin esta alineación el reconocimiento degrada mucho.

Salida: embedding L2-normalizado - así la similitud de coseno es un simple
producto punto (NumPy, 0.23 ms contra 5000 alumnos, medido en el §0).
"""
import cv2
import numpy as np
import onnxruntime as ort

# Destinos de los 5 landmarks para la entrada 112x112 (convención ArcFace):
# ojo izq, ojo der, nariz, comisura izq, comisura der.
_ARCFACE_DST = np.float32(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ]
)

# Normalización del embedder (misma familia det_10g: centrado en 127.5).
EMB_MEAN = 127.5
EMB_STD = 127.5

def estimate_norm(lmk: np.ndarray, image_size: int = 112) -> tuple[np.ndarray, float]:
    """Similitud transform landmarks→destino. Devuelve (matriz 2x3, escala).

    Usa ``cv2.estimateAffinePartial2D`` (rotación+escala+traslación, 4 g.d.l.),
    el equivalente en opencv estándar de ``cv2.SimilarityTransform`` (contrib).
    """
    assert lmk.shape == (5, 2), f"landmarks con forma inesperada: {lmk.shape}"
    ratio = float(image_size) / 112.0
    dst = _ARCFACE_DST * ratio
    m, _ = cv2.estimateAffinePartial2D(
        lmk.reshape(5, 2).astype(np.float32), dst.astype(np.float32), method=cv2.LMEDS
    )
    assert m is not None, "no se pudo estimar la transform de alineación"
    return m, 0.0


def normed_embedding(embedding: np.ndarray) -> np.ndarray:
    return embedding / np.linalg.norm(embedding)


class ArcFaceEmbedder:
    """Extrae el embedding 512-d de un rostro alineado (o frame + landmarks)."""

    def __init__(self, model_path: str) -> None:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_size = (
            int(shape[3]) if isinstance(shape[3], int) else 112,  # (W, H)
            int(shape[2]) if isinstance(shape[2], int) else 112,
        )
        out_shape = self.session.get_outputs()[0].shape
        last = out_shape[-1] if isinstance(out_shape, list | tuple) and out_shape else 512
        self.output_dim = int(last) if isinstance(last, int) else 512

    def aligned_crop(self, frame: np.ndarray, lmk: np.ndarray) -> np.ndarray:
        """Alinea el rostro: warp afín landmarks→arcface112 (RGB, normalizado)."""
        m, _ = estimate_norm(lmk, image_size=112)
        warped = cv2.warpAffine(frame, m, self.input_size, borderValue=0.0)
        img = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - EMB_MEAN) / EMB_STD
        return np.transpose(img, (2, 0, 1))[None]  # (1,3,112,112)

    def get(self, frame: np.ndarray, lmk: np.ndarray) -> np.ndarray:
        """Embedding L2-normalizado (512,) a partir del frame y sus landmarks."""
        blob = self.aligned_crop(frame, lmk)
        emb = self.session.run(None, {self.input_name: blob})[0].flatten()
        return normed_embedding(emb.astype(np.float32))

    def get_from_crop(self, aligned_rgb_norm: np.ndarray) -> np.ndarray:
        """Variante por si el llamador ya tiene el blob alineado (tests)."""
        emb = self.session.run(None, {self.input_name: aligned_rgb_norm})[0].flatten()
        return normed_embedding(emb.astype(np.float32))
