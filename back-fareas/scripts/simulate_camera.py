import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from app.ai.frame_source import draw_face, open_source
from app.ai.pipeline import COLORS, MESSAGES
from app.ai.resources import demo_video
from app.ai.runtime import vision_pipeline


async def _galeria_desde_bd() -> int:
    from app.ai.runtime import recargar_galeria
    from app.database import SessionLocal

    async with SessionLocal() as db:
        n = await recargar_galeria(db)
    from app.database import engine

    await engine.dispose()
    return n

def main() -> None:
    parser = argparse.ArgumentParser(description="Demo de reconocimiento facial Fareas")
    parser.add_argument("source", nargs="?", default=None, help="mp4/avi, rtsp:// o 0 (webcam); defecto: video demo del proyecto")
    parser.add_argument("--thr", type=float, default=0.75, help="umbral de similitud (RF-20)")
    parser.add_argument("--save", default=None, help="guardar video anotado en esta ruta")
    parser.add_argument("--fps", type=float, default=2.0, help="frames procesados por segundo")
    parser.add_argument("--max-frames", type=int, default=0, help="tope de frames a grabar (0 = video completo)")
    args = parser.parse_args()
    if args.source is None:
        args.source = str(demo_video())

    n_alumnos = asyncio.run(_galeria_desde_bd())
    pipe = vision_pipeline(threshold=args.thr)
    print(f"[Fareas] galeria: {n_alumnos} alumnos | umbral: {args.thr} | fuente: {args.source}")

    src = open_source(args.source)

    import time

    def primer_frame(fuente, intentos: int = 80):
        for _ in range(intentos):
            ok, f = fuente.read()
            if ok and f is not None:
                return f
            time.sleep(0.05)
        return None

    primero = primer_frame(src)
    if primero is None:
        print("La fuente no entrega frames (ruta/stream invalido)")
        return
    writer = None
    limite_frames = 0
    if args.save:
        writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), 24.0,
                                 (primero.shape[1], primero.shape[0]))
        probe = cv2.VideoCapture(str(args.source))
        limite_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or 250
        probe.release()
        if args.max_frames:
            limite_frames = min(limite_frames, args.max_frames)

    frame = primero
    fallos = 0
    escritos = 0

    ultimo = {}
    try:
        while True:
            t0 = time.monotonic()
            ok, frame = src.read()
            if not ok or frame is None:
                fallos += 1
                if fallos > 20:
                    break
                time.sleep(0.05)
                continue
            fallos = 0
            resultado = pipe.process_frame(frame)
            if resultado.faces:
                color = COLORS.get(resultado.color, (255, 255, 255))
                etiqueta = f"{resultado.verdict} {resultado.similarity:.2f}"
                frame = draw_face(frame, resultado.box, color, etiqueta)
                ultimo = {"verdict": resultado.verdict, "sim": round(resultado.similarity, 3),
                          "student": resultado.student_id}
            cv2.putText(frame, f"galeria={n_alumnos} | {MESSAGES.get(resultado.verdict, '')}",
                        (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            if writer is not None:
                writer.write(frame)
                escritos += 1
                if escritos >= limite_frames:
                    print(f"video anotado completo: {escritos} frames -> {args.save}")
                    break
            else:
                cv2.imshow("Fareas - demo puerta (q = salir)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            dt = time.monotonic() - t0
            time.sleep(max(0.0, 1.0 / args.fps - dt))
            if ultimo:
                print(ultimo)
    finally:
        src.release()
        if writer is not None:
            writer.release()
        else:
            cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
