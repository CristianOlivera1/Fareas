"""R2 (ventana de marca) y R7 (niveles DPI) — pruebas PURAS, sin BD.

Tabla del Bloque 11 §2: bloque 08:00-10:00, tolerancia T=10 min, apertura
anticipada E=15 min:
    07:44 → sin sesión · 07:45-08:10 → asistio · 08:11-10:00 → tardanza ·
    10:01 → cerrada (la falta la genera el cierre).
"""
from datetime import date, datetime, time
from types import SimpleNamespace

from app.services.attendance_engine import clasificar
from app.services.dpi import nivel_de

FECHA = date(2026, 10, 12)  # lunes


def _bloque(start: time, end: time) -> SimpleNamespace:
    return SimpleNamespace(start_time=start, end_time=end)


def _cfg(*, early: int = 15, tolerance: int = 10, alerta: float = 20.0, limite: float = 30.0) -> SimpleNamespace:
    return SimpleNamespace(
        early_open_minutes=early, late_tolerance_minutes=tolerance,
        dpi_alert_percent=alerta, dpi_limit_percent=limite,
    )


def _dt(hhmm: str) -> datetime:
    hh, mm = map(int, hhmm.split(":"))
    return datetime.combine(FECHA, time(hh, mm))


def test_tabla_de_ventana_r2():
    bloque = _bloque(time(8, 0), time(10, 0))
    cfg = _cfg()
    casos = [
        ("07:44", None),      # antes de apertura − E
        ("07:45", "asistio"),  # inicio − E
        ("08:00", "asistio"),  # inicio exacto
        ("08:10", "asistio"),  # inicio + T (incluido)
        ("08:11", "tardanza"),  # primer segundo de tardanza
        ("09:59", "tardanza"),
        ("10:00", "tardanza"),  # fin del bloque: 55 min tarde sigue siendo tardanza
        ("10:01", None),       # ventana cerrada → falta al cierre
        ("23:00", None),
    ]
    for hhmm, esperado in casos:
        assert clasificar(_dt(hhmm), bloque, FECHA, cfg) == esperado, f"{hhmm} → {esperado}"


def test_ventana_con_tolerancia_cero():
    """T=0: solo el instante exacto del inicio es 'asistio'."""
    bloque = _bloque(time(8, 0), time(9, 0))
    cfg = _cfg(tolerance=0)
    assert clasificar(_dt("08:00"), bloque, FECHA, cfg) == "asistio"
    assert clasificar(_dt("08:01"), bloque, FECHA, cfg) == "tardanza"


def test_nivel_dpi_al_superar_no_al_alcanzar():
    """Decisión del usuario: inhabilitación al SUPERAR el 30 % (no al alcanzarlo)."""
    cfg = _cfg(alerta=20.0, limite=30.0)
    assert nivel_de(0.0, cfg) is None
    assert nivel_de(19.99, cfg) is None
    assert nivel_de(20.0, cfg) == "alerta"   # aviso preventivo (≥ 20)
    assert nivel_de(25.0, cfg) == "alerta"
    assert nivel_de(30.0, cfg) == "alerta"   # alcanzar el límite NO inhabilita
    assert nivel_de(30.01, cfg) == "limite"  # superarlo SÍ
    assert nivel_de(100.0, cfg) == "limite"
