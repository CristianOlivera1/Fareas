from app.services.emailer import send_email


async def send_dpi_alert(
    to: str,
    full_name: str,
    course_code: str,
    sessions: int,
    absences: int,
    percent: float,
    umbral: float,
    nivel: str = "alerta",
) -> bool:
    import html

    limite = nivel == "limite"
    encabezado = "Inhabilitación por inasistencias (DPI)" if limite else "Alerta de inasistencias"
    subject = f"Fareas UNAMBA - {encabezado} en {course_code}"
    safe_name = html.escape(full_name)
    safe_course = html.escape(course_code)
    color = "#B42318" if limite else "#155DFC"
    aviso = (
        f"Has SUPERADO el {umbral:.0f} % límite de inasistencias: quedarás inhabilitado "
        "en este curso si el reglamento lo confirma."
        if limite
        else f"Has alcanzado el {percent:.0f} % de inasistencias (aviso preventivo; "
        f"el límite es {umbral:.0f} %)."
    )

    plain = (
        f"Hola {full_name},\n\n"
        f"Según el registro de asistencia del curso {course_code}:\n\n"
        f"  Sesiones dictadas: {sessions}\n"
        f"  Inasistencias: {absences} ({percent:.1f} %)\n\n"
        f"{aviso}\n\n"
        "Recuerda que las faltas justificadas (descansos médicos) no cuentan; "
        "si tienes uno, entrégalo en secretaría académica (RF-10).\n\n"
        "- Sistema Fareas, Facultad de Informática UNAMBA"
    )
    content_html = (
        f'<p style="margin:0;">Hola <strong>{safe_name}</strong>,</p>'
        f'<p style="margin:12px 0 0;">Según el registro de asistencia del curso '
        f'<strong>{safe_course}</strong>:</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:16px 0;width:100%;">'
        f'<tr><td style="padding:10px 12px;background-color:#F6F9FF;border:1px solid #E5E7EB;'
        f'border-radius:8px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
        f'font-size:14px;color:#111827;">'
        f'Sesiones dictadas: <strong>{sessions}</strong><br>'
        f'Inasistencias: <strong>{absences}</strong> ({percent:.1f} %)</td></tr></table>'
        f'<p style="margin:12px 0 0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
        f'font-size:14px;color:{color};font-weight:700;">{aviso}</p>'
        f'<p style="margin:8px 0 0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;'
        f'font-size:13px;color:#374151;">'
        f'Las faltas justificadas no cuentan para el límite. Si tienes un descanso '
        f'médico, entrégalo en secretaría (RF-10).</p>'
    )
    html_body = (
        f'<!doctype html><html lang="es"><body style="margin:0;background:#F6F9FF;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#F6F9FF;padding:24px 12px;"><tr><td align="center">'
        f'<table role="presentation" width="600" style="max-width:600px;background:#fff;'
        f'border:1px solid #E5E7EB;border-radius:12px;">'
        f'<tr><td style="padding:28px 28px 0;font-family:Arial,sans-serif;font-size:20px;'
        f'font-weight:700;color:#111827;">Fareas<span style="color:#155DFC;">.</span></td></tr>'
        f'<tr><td style="padding:20px 28px 0;font-family:Arial,sans-serif;font-size:18px;'
        f'font-weight:700;color:{color};">{encabezado}</td></tr>'
        f'<tr><td style="padding:12px 28px;font-family:Arial,sans-serif;font-size:14px;'
        f'line-height:1.6;color:#374151;">{content_html}</td></tr>'
        f'<tr><td style="padding:0 28px 28px;font-family:Arial,sans-serif;font-size:11px;'
        f'color:#9CA3AF;">© Fareas · Facultad de Informática UNAMBA</td></tr>'
        f'</table></td></tr></table></body></html>'
    )
    return await send_email(to, subject, plain, html_body)
