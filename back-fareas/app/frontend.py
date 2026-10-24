from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse


def resolve_dist_dir(configured: str) -> Path | None:
    if not configured.strip():
        return None
    base = Path(configured)
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent / base
    base = base.resolve()
    return base if (base / "index.html").is_file() else None


def mount_frontend(app: FastAPI, dist_dir: Path, reserved_prefixes: tuple[str, ...]) -> None:
    root = dist_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_frontend(path: str) -> FileResponse:
        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in reserved_prefixes):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
