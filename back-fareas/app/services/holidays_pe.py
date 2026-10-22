from datetime import date


def _pascua(anio: int) -> tuple[int, int]:
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return mes, dia

def _desde_pascua(anio: int, dias: int) -> tuple[int, int]:
    from datetime import date, timedelta

    mes, dia = _pascua(anio)
    p = date(anio, mes, dia) + timedelta(days=dias)
    return p.month, p.day

def feriados_nacionales(anio: int) -> list[tuple[date, str]]:
    fijos = [
        ("01-01", "Año Nuevo"),
        ("05-01", "Día del Trabajo"),
        ("06-07", "Batalla de Arica y Día de la Bandera"),
        ("06-29", "San Pedro y San Pablo"),
        ("07-23", "Día de la Fuerza Aérea del Perú"),
        ("07-28", "Fiestas Patrias"),
        ("07-29", "Fiestas Patrias"),
        ("08-06", "Batalla de Junín"),
        ("08-30", "Santa Rosa de Lima"),
        ("10-08", "Combate de Angamos"),
        ("11-01", "Día de Todos los Santos"),
        ("12-08", "Inmaculada Concepción"),
        ("12-09", "Batalla de Ayacucho"),
        ("12-25", "Navidad"),
    ]
    moviles = [
        (_desde_pascua(anio, -3), "Jueves Santo"),
        (_desde_pascua(anio, -2), "Viernes Santo"),
    ]
    out = [(date(anio, int(md[:2]), int(md[3:])), desc) for md, desc in fijos]
    out += [(date(anio, mes, dia), desc) for (mes, dia), desc in moviles]
    return sorted(out, key=lambda par: par[0])
