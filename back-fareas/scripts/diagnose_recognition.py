import argparse
import asyncio
import logging
import time

import cv2
from sqlalchemy import text

from app.ai.runtime import detector, embedder, gallery, recargar_galeria
from app.database import SessionLocal

logging.disable(logging.CRITICAL)


async def _cargar(room_code: str | None, rtsp: str | None) -> tuple[str, dict[int, str]]:
    async with SessionLocal() as db:
        if rtsp is None:
            consulta = (
                "select d.device_key, r.code, d.rtsp_url, d.is_online from device d join room r on r.id = d.room_id "
                "where d.device_type = 'camara' and d.is_active and d.rtsp_url is not null"
            )
            parametros = {}
            if room_code:
                consulta += " and r.code = :code"
                parametros["code"] = room_code
            filas = (await db.exec(text(consulta + " order by d.is_online desc, d.last_heartbeat desc nulls last").bindparams(**parametros))).all()
            if not filas:
                raise SystemExit("No hay cámara activa con RTSP para ese aula")
            print("Cámaras activas:")
            for clave, aula, _url, en_linea in filas:
                print(f"  {clave} ({aula}) {'en línea' if en_linea else 'sin conexión'}")
            rtsp = filas[0][2]
            print(f"Usando {filas[0][0]}. Si no es la tuya, pasa --room CODIGO o --rtsp URL")
        nombres = {
            r[0]: f"{r[1]} ({r[2]})"
            for r in (await db.exec(text("select id, full_name, code from app_user where role = 'estudiante'"))).all()
        }
        await recargar_galeria(db)
    return rtsp, nombres


def main() -> None:
    parser = argparse.ArgumentParser(description="Mide la similitud en vivo contra los alumnos enrolados")
    parser.add_argument("--room", help="Código del aula (por defecto, la primera cámara activa)")
    parser.add_argument("--rtsp", help="URL RTSP completa (anula la base de datos)")
    parser.add_argument("--seconds", type=int, default=20)
    args = parser.parse_args()

    rtsp, nombres = asyncio.run(_cargar(args.room, args.rtsp))
    det, emb, galeria = detector(), embedder(), gallery()
    captura = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    if not captura.isOpened():
        raise SystemExit("No se pudo abrir el stream de la cámara")
    print(f"Alumnos enrolados: {len(galeria)}. Mírate a la cámara durante {args.seconds} s…")
    limite = time.monotonic() + args.seconds
    muestras = 0
    mejores: dict[int, float] = {}
    while time.monotonic() < limite:
        ok, frame = captura.read()
        if not ok:
            continue
        rostros = det.detect(frame, max_faces=1)
        if not rostros:
            continue
        rostro = rostros[0]
        lado = int(min(rostro.box[2] - rostro.box[0], rostro.box[3] - rostro.box[1]))
        similitudes = galeria.best_similarities(emb.get(frame, rostro.kps))
        muestras += 1
        for sid, valor in similitudes.items():
            mejores[sid] = max(mejores.get(sid, 0.0), valor)
        top = sorted(similitudes.items(), key=lambda par: par[1], reverse=True)[:2]
        detalle = " | ".join(f"{nombres.get(sid, sid)}: {valor:.2f}" for sid, valor in top)
        print(f"rostro {lado:>3}px  score {rostro.score:.2f}  {detalle}")
    captura.release()
    print(f"\nMuestras con rostro: {muestras}")
    for sid, valor in sorted(mejores.items(), key=lambda par: par[1], reverse=True):
        print(f"  máxima similitud con {nombres.get(sid, sid)}: {valor:.2f}")


if __name__ == "__main__":
    main()
