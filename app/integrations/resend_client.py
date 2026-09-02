"""Resend integration for transactional email, with an automatic
development fallback.

See the plan's "Contrato del fallback de terceros" — summarized here:

- Activates ONLY when RESEND_API_KEY is absent. There is no flag to force
  either path; the real integration is always used when credentials exist.
- Never masks a failure: if credentials are present and the Resend call
  fails, the exception propagates — it does not fall back to the outbox.
- Is unmistakable: a startup warning, a per-send warning, and every
  outbox file carries a header saying it was never actually sent.
- `Settings._forbid_dev_fallback_in_production` (app/core/config.py)
  already refuses to start in production without real credentials, so
  this module never needs to guard against that itself.
"""

from __future__ import annotations

import logging
from pathlib import Path

import resend

from app.core.config import settings
from app.core.time import utcnow

logger = logging.getLogger(__name__)

_OUTBOX_DIR = Path("outbox")

if settings.email_mode == "resend":
    resend.api_key = settings.resend_api_key
else:
    logger.warning(
        "[MODO DEV] RESEND_API_KEY ausente -> los correos se escriben en "
        "./outbox/, NO se envian de verdad."
    )


def _write_to_outbox(*, to_email: str, subject: str, html: str) -> Path:
    _OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = utcnow().strftime("%Y%m%d%H%M%S%f")
    safe_recipient = to_email.replace("@", "_at_").replace("/", "_")
    path = _OUTBOX_DIR / f"{timestamp}_{safe_recipient}.html"

    header = (
        f"<!-- MODO DEV: este correo NUNCA fue enviado de verdad. "
        f"Destinatario: {to_email} | Asunto: {subject} | "
        f"Generado: {utcnow().isoformat()} -->\n"
    )
    path.write_text(header + html, encoding="utf-8")
    logger.warning("[MODO DEV] Correo simulado para %s guardado en %s", to_email, path)
    return path


def _send(*, to_email: str, subject: str, html: str) -> None:
    if settings.email_mode != "resend":
        _write_to_outbox(to_email=to_email, subject=subject, html=html)
        return

    resend.Emails.send(
        {
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
    )


def send_verification_email(*, to_email: str, code: str) -> None:
    subject = "Verifica tu cuenta de GameVault UCN"
    html = (
        "<p>Gracias por registrarte en GameVault UCN.</p>"
        f"<p>Tu codigo de verificacion es:</p><h2>{code}</h2>"
        f"<p>Expira en {settings.verification_code_ttl_minutes} minutos. "
        "Si no fuiste tu, puedes ignorar este correo.</p>"
    )
    _send(to_email=to_email, subject=subject, html=html)
