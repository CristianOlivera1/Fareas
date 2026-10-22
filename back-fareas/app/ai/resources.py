from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parents[2] / "resources"

DEMO_VIDEO = "377973_medium.mp4"


def demo_video() -> Path:
    path = RESOURCES_DIR / DEMO_VIDEO
    if not path.exists():
        raise FileNotFoundError(
            f"Falta {path}. Copia el video de demo a back-fareas/resources/ "
            "(ver README, sección Recursos)."
        )
    return path
