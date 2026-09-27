"""Recursos binarios del proyecto (no versionados por git, pero DENTRO del repo).

`back-fareas/resources/` guarda los pesos de demo y videos de prueba; el
gitignore los excluye (son binarios grandes), pero las rutas son relativas al
proyecto para que el repo sea autocontenido: si el usuario copia la carpeta,
los demos siguen funcionando sin rutas absolutas de Downloads.

`demo_video()` devuelve el video de la "puerta del aula" usado por los tests
smoke y por `scripts/simulate_camera.py` (antes vivía en Downloads).
"""
from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parents[2] / "resources"

DEMO_VIDEO = "377973_medium.mp4"


def demo_video() -> Path:
    """Ruta del video de demo dentro del proyecto (excepción clara si falta)."""
    path = RESOURCES_DIR / DEMO_VIDEO
    if not path.exists():
        raise FileNotFoundError(
            f"Falta {path}. Copia el video de demo a back-fareas/resources/ "
            "(ver README, sección Recursos)."
        )
    return path
