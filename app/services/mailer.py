import smtplib
from email.mime.text import MIMEText
from typing import Iterable, Optional
from app.config import settings

def send_email(subject: str, body_text: str, to: Iterable[str], body_html: Optional[str] = None):
    """
    The simplest synchronous sending via smtplib. Works with Mailpit/MailHog.
    If settings.smtp_tls=True — use STARTTLS.
    """
    to_list = list(to)
    msg = MIMEText(body_html or body_text, "html" if body_html else "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to_list)

    if settings.smtp_tls:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        server.starttls()
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)

    try:
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_pass)
        server.sendmail(settings.smtp_from, to_list, msg.as_string())
    finally:
        server.quit()


def send_verify_email(email: str, token: str):
    # if you want to click directly on the API, use APP_BASE_URL= http://localhost:8000
    link = f"{settings.frontend_origin}/auth/verify?token={token}"
    # Alternative to API link: f"{settings.database_url}/auth/verify?token={token}" — but better front
    subject = "Verify your email"
    text = f"Hello!\nConfirm your email: {link}"
    html = f"""<p>Hello!</p><p>Confirm your email: <a href="{link}">{link}</a></p>"""
    send_email(subject, text, [email], body_html=html)
