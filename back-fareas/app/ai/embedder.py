import cv2
import numpy as np
import onnxruntime as ort

_ARCFACE_DST = np.float32(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ]
)

EMB_MEAN = 127.5
EMB_STD = 127.5

def estimate_norm(lmk: np.ndarray, image_size: int = 112) -> tuple[np.ndarray, float]:
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
    def __init__(self, model_path: str) -> None:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_size = (
            int(shape[3]) if isinstance(shape[3], int) else 112,
            int(shape[2]) if isinstance(shape[2], int) else 112,
        )
        out_shape = self.session.get_outputs()[0].shape
        last = out_shape[-1] if isinstance(out_shape, list | tuple) and out_shape else 512
        self.output_dim = int(last) if isinstance(last, int) else 512

    def aligned_crop(self, frame: np.ndarray, lmk: np.ndarray) -> np.ndarray:
        m, _ = estimate_norm(lmk, image_size=112)
        warped = cv2.warpAffine(frame, m, self.input_size, borderValue=0.0)
        img = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB).astype(np.float32)
        img = (img - EMB_MEAN) / EMB_STD
        return np.transpose(img, (2, 0, 1))[None]

    def get(self, frame: np.ndarray, lmk: np.ndarray) -> np.ndarray:
        blob = self.aligned_crop(frame, lmk)
        emb = self.session.run(None, {self.input_name: blob})[0].flatten()
        return normed_embedding(emb.astype(np.float32))

    def get_from_crop(self, aligned_rgb_norm: np.ndarray) -> np.ndarray:
        emb = self.session.run(None, {self.input_name: aligned_rgb_norm})[0].flatten()
        return normed_embedding(emb.astype(np.float32))
