import argparse
import asyncio
import json
import pathlib
import sys

import websockets

WS_URL = "ws://localhost:8000/api/v1/ws/devices"

COLORES = {"verde": "\033[92m", "amarillo": "\033[93m", "rojo": "\033[91m", "azul": "\033[94m"}
RESET = "\033[0m"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador del nodo ESP32 Fareas")
    parser.add_argument("device_key", nargs="?", default="esp32-lab305")
    parser.add_argument("--intervalo", type=int, default=5, help="segundos entre heartbeats")
    args = parser.parse_args()

    env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    token = ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEVICE_TOKEN_SECRET="):
            token = line.split("=", 1)[1].strip()
            break
    if not token:
        print("DEVICE_TOKEN_SECRET no encontrado en .env")
        sys.exit(1)

    print(f"Conectando como '{args.device_key}' a {WS_URL} ...")
    try:
        async with websockets.connect(f"{WS_URL}?token={token}") as ws:
            await ws.send(json.dumps({"type": "hello", "device_id": args.device_key, "mac": "AA:BB:CC:DD:EE:FF"}))
            print(f"<- {await ws.recv()}")

            async def heartbeats() -> None:
                while True:
                    await asyncio.sleep(args.intervalo)
                    await ws.send(json.dumps({"type": "heartbeat"}))

            hb = asyncio.create_task(heartbeats())

            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "verdict":
                        color = COLORES.get(msg.get("color", ""), "")
                        buzzer = msg.get("buzzer", "-")
                        etiqueta = "(sin beeps)" if buzzer == "ninguno" else ""
                        print(f"{color}[LED {msg.get('color', '?').upper():8}] buzzer={buzzer:14} "
                              f"{msg.get('seconds', 0)}s  {msg.get('message', '')}{RESET} "
                              f"{etiqueta} (status={msg.get('status')})")
                    else:
                        print(f"<- {raw}")
            except websockets.ConnectionClosed as e:
                print(f"Conexion cerrada por el backend (code={e.rcvd.code if e.rcvd else '?'})")
            finally:
                hb.cancel()
    except ConnectionRefusedError:
        print("No se pudo conectar: ¿el backend esta corriendo? (fastapi dev)")

if __name__ == "__main__":
    asyncio.run(main())
