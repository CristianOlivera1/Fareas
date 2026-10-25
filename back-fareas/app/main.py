from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.frontend import mount_frontend, resolve_dist_dir
from app.routers import (
    attendance,
    audit,
    auth,
    calendar_admin,
    catalog,
    course_groups,
    courses,
    curriculum,
    dashboard,
    dpi,
    enrollment_center,
    enrollment_faces,
    health,
    me,
    notifications,
    pilot,
    profile,
    reports,
    self_enrollment,
    ws_devices,
)
from app.services import errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"[Fareas] {settings.APP_NAME} arrancando en modo {settings.ENVIRONMENT}")

    from app.services.camera_loop import detener_bucle_camaras, iniciar_bucle_camaras
    from app.services.session_scheduler import detener_scheduler, iniciar_scheduler

    iniciar_scheduler(intervalo_segundos=60)
    iniciar_bucle_camaras()
    print("[Fareas] Scheduler RF-26 + notificaciones + bucle de camaras activos")

    yield

    await detener_bucle_camaras()
    detener_scheduler()
    print("[Fareas] Cerrando conexiones (pool de BD, sockets de dispositivos)...")

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(errors.DomainError)
    async def domain_error_handler(_request: Request, exc: errors.DomainError) -> JSONResponse:
        code = {
            errors.ConflictError: status.HTTP_409_CONFLICT,
            errors.NotFoundError: status.HTTP_404_NOT_FOUND,
        }.get(type(exc), status.HTTP_422_UNPROCESSABLE_CONTENT)
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        resumen = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', [])[1:]) or 'cuerpo'}: {e.get('msg', 'inválido')}"
            for e in exc.errors()
        )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": resumen})

    app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
    app.include_router(health.router, prefix=settings.API_V1_PREFIX)
    app.include_router(ws_devices.router, prefix=settings.API_V1_PREFIX)
    app.include_router(catalog.router, prefix=settings.API_V1_PREFIX)
    app.include_router(course_groups.router, prefix=settings.API_V1_PREFIX)
    app.include_router(courses.router, prefix=settings.API_V1_PREFIX)
    app.include_router(curriculum.router, prefix=settings.API_V1_PREFIX)
    app.include_router(calendar_admin.router, prefix=settings.API_V1_PREFIX)
    app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
    app.include_router(dpi.router, prefix=settings.API_V1_PREFIX)
    app.include_router(enrollment_faces.router, prefix=settings.API_V1_PREFIX)
    app.include_router(attendance.router, prefix=settings.API_V1_PREFIX)
    app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
    app.include_router(reports.router, prefix=settings.API_V1_PREFIX)
    app.include_router(me.router, prefix=settings.API_V1_PREFIX)
    app.include_router(enrollment_center.router, prefix=settings.API_V1_PREFIX)
    app.include_router(self_enrollment.router, prefix=settings.API_V1_PREFIX)
    app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
    app.include_router(profile.router, prefix=settings.API_V1_PREFIX)
    app.include_router(pilot.router, prefix=settings.API_V1_PREFIX)

    dist_dir = resolve_dist_dir(settings.FRONTEND_DIST_DIR)
    if dist_dir is not None:
        reserved = (settings.API_V1_PREFIX.strip("/"), "docs", "redoc", "openapi.json")
        mount_frontend(app, dist_dir, reserved)

    return app

app = create_app()
