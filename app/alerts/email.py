import smtplib
from email.mime.text import MIMEText

from app.config import settings


def send_alert(
    object_name: str,
    device_name: str,
    error_type: str,
    value: float,
    previous: float | None = None,
):
    if not settings.ALERT_EMAIL_TO:
        return

    subject = f"⚠️ ELDIS ALERT - {error_type}"
    body = f"""⚠️ ELDIS ALERT

Object: {object_name}
Device: {device_name}
Error: {error_type}
Value: {value}
Previous: {previous}

Time: {settings.ELDIS_API_URL}
"""

    recipients = [e.strip() for e in settings.ALERT_EMAIL_TO.split(",")]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.ALERT_EMAIL_FROM
    msg["To"] = ", ".join(recipients)

    if settings.ALERT_SMTP_HOST:
        if settings.ALERT_SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_PORT) as server:
                server.login(settings.ALERT_SMTP_USER, settings.ALERT_SMTP_PASSWORD)
                server.sendmail(settings.ALERT_EMAIL_FROM, recipients, msg.as_string())
        else:
            with smtplib.SMTP(settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_PORT) as server:
                server.starttls()
                server.login(settings.ALERT_SMTP_USER, settings.ALERT_SMTP_PASSWORD)
                server.sendmail(settings.ALERT_EMAIL_FROM, recipients, msg.as_string())
