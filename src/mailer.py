"""Email through Gmail (an App Password — Google account → Security → App passwords). Secrets: GMAIL_ADDRESS,
GMAIL_APP_PASSWORD; recipient: settings email_to (default: the same address)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from . import common


def send(subject: str, html: str, attachments: list[Path] | None = None, to: str | None = None) -> None:
    sender = os.getenv('GMAIL_ADDRESS', '')
    pw = os.getenv('GMAIL_APP_PASSWORD', '')
    to = to or common.settings()['email_to'] or sender
    if not sender or not pw:
        raise RuntimeError('GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set')
    msg = EmailMessage()
    msg['Subject'], msg['From'], msg['To'] = subject, sender, to
    msg.set_content('הודעה זו בנויה ב-HTML — פתח אותה בתוכנת מייל רגילה.')
    msg.add_alternative(html, subtype='html')
    for p in attachments or []:
        p = Path(p)
        sub = 'pdf' if p.suffix.lower() == '.pdf' else ('html' if p.suffix.lower() == '.html' else 'octet-stream')
        maintype = 'text' if sub == 'html' else 'application'
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=sub, filename=p.name)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=60) as smtp:
        smtp.login(sender, pw)
        smtp.send_message(msg)
