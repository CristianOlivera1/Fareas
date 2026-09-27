"""Prueba rápida de la cámara Hikvision por RTSP (RF-17) - PLAN §4.1.

Uso:
    cd back-fareas
    .venv/Scripts/python scripts/test_rtsp.py "rtsp://admin:CONTRASEÑA@10.14.5.11:554/Streaming/Channels/102"
    .venv/Scripts/python scripts/test_rtsp.py --list   # URLs de ejemplo del seed

Muestra resolución/fps y guarda el primer frame en storage/test_rtsp.jpg.
Recomendación: usar el SUB-STREAM (Channels/102) para el pipeline: menos CPU.
"""
import sys
from pathlib import Path

import cv2  # type: ignore[import-untyped]

STORAGE = Path(__file__).resolve().parent.parent / "storage"


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        print(__doc__)
        sys.exit(0)

    url = sys.argv[1]
    print(f"Conectando a {url.split('@')[-1]} …")
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print("❌ No se pudo abrir el stream. Revisa: IP, usuario/contraseña, firewall o que la")
        print("   cámara esté activada (herramienta SADP de Hikvision) y reachable con ping.")
        sys.exit(1)

    ok, frame = cap.read()
    if not ok:
        print("❌ Conectó pero no entregó frames (prueba el otro canal 101/102).")
        sys.exit(1)

    height, width = frame.shape[:2]
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"✅ Stream OK - {width}x{height} @ {fps:.1f} fps")

    STORAGE.mkdir(exist_ok=True)
    out = STORAGE / "test_rtsp.jpg"
    cv2.imwrite(str(out), frame)
    print(f"🖼️  Primer frame guardado en: {out}")

    cap.release()


if __name__ == "__main__":
    main()
