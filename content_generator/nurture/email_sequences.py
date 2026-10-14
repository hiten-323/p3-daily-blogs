"""
Email nurture sequences — SMTP-based, stage-triggered.

Sends personalised emails to leads based on their current pipeline stage.
Integrates with the same template system as WhatsApp for consistency.

Requirements:
  SMTP_HOST=smtp.gmail.com   (or your provider)
  SMTP_PORT=587
  SMTP_USER=your@email.com
  SMTP_PASS=your_app_password
  NURTURE_FROM_NAME=Purity Beans Team
  NURTURE_FROM_EMAIL=hello@p3online.in

Usage:
    from content_generator.nurture.email_sequences import send_email

    send_email(
        to_email="rajesh@sharmadistributors.com",
        to_name="Rajesh",
        segment="distributor",
        stage="inquiry",
        lead_id="dist_20260609_001",
    )

All sends are logged to nurture_log in the SQLite DB.
"""
from __future__ import annotations
import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_SEND_LOCK = threading.Lock()   # serialise SMTP sends (single connection)


def is_configured() -> bool:
    """Return True if SMTP credentials are present."""
    return bool(os.getenv("SMTP_USER")) and bool(os.getenv("SMTP_PASS"))


def send_email(
    to_email: str,
    to_name: str     = "",
    segment: str     = "consumer",
    stage: str       = "inquiry",
    lead_id: str     = "",
    extra_vars: dict = None,
) -> dict:
    """
    Send a nurture email for the given segment/stage.

    Looks up the template, renders it, and sends via SMTP.

    Returns:
        {"success": bool, "error": str|None}
    """
    if not is_configured():
        logger.warning("[email] Not configured — SMTP_USER / SMTP_PASS missing")
        return {"success": False, "error": "not_configured"}

    if not to_email:
        return {"success": False, "error": "no_email"}

    from content_generator.nurture.templates import render_template

    vars_ = {"name": to_name or "there", **(extra_vars or {})}
    tmpl  = render_template(segment, stage, **vars_)

    if not tmpl:
        logger.debug("[email] No template for (%s, %s) — skipping %s", segment, stage, lead_id)
        return {"success": False, "error": "no_template"}

    if tmpl["channel"] not in ("email", "both"):
        return {"success": False, "error": "email_not_in_channel"}

    subject = tmpl["subject"]
    body    = tmpl["body"] + f"\n\n---\n{tmpl['cta']}"

    result = _send_smtp(to_email=to_email, to_name=to_name, subject=subject, body=body)
    _log_nurture(lead_id, segment, stage, "email", result)
    return result


def send_raw_email(
    to_email: str,
    subject: str,
    body: str,
    to_name: str = "",
    lead_id: str = "",
    segment: str = "",
    stage: str   = "",
) -> dict:
    """Send a custom email not tied to any template."""
    if not is_configured():
        return {"success": False, "error": "not_configured"}

    result = _send_smtp(to_email=to_email, to_name=to_name, subject=subject, body=body)
    _log_nurture(lead_id, segment, stage, "email_raw", result)
    return result


def _send_smtp(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
) -> dict:
    """Low-level SMTP send using environment credentials."""
    host      = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port      = int(os.getenv("SMTP_PORT", "587"))
    user      = os.getenv("SMTP_USER", "")
    password  = os.getenv("SMTP_PASS", "")
    from_name = os.getenv("NURTURE_FROM_NAME", "Purity Beans Team")
    from_addr = os.getenv("NURTURE_FROM_EMAIL", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_addr}>"
    msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email

    # Plain text part
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # HTML part — simple branded wrapper
    html_body = _wrap_html(body, subject)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with _SEND_LOCK:
        try:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(user, password)
                server.sendmail(from_addr, [to_email], msg.as_string())

            logger.info("[email] Sent '%s' to %s", subject, to_email)
            return {"success": True, "error": None}

        except smtplib.SMTPAuthenticationError as e:
            logger.error("[email] Auth error: %s", e)
            return {"success": False, "error": "smtp_auth_failed"}

        except smtplib.SMTPRecipientsRefused as e:
            logger.warning("[email] Recipient refused: %s", e)
            return {"success": False, "error": "recipient_refused"}

        except Exception as e:
            logger.error("[email] SMTP error: %s", e)
            return {"success": False, "error": str(e)}


def _wrap_html(plain_text: str, subject: str) -> str:
    """Wrap plain text in a minimal branded HTML email."""
    # Escape HTML entities and convert newlines to <br>
    import html as html_lib
    safe = html_lib.escape(plain_text).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(subject)}</title>
</head>
<body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
  <table width="600" cellpadding="0" cellspacing="0" style="background: #0D0905; border-radius: 8px; margin: 0 auto;">
    <tr>
      <td style="padding: 20px 30px; border-bottom: 3px solid #C8962E;">
        <h2 style="color: #C8962E; margin: 0; font-size: 20px;">PURITY BEANS</h2>
        <p style="color: #F5EED8; font-size: 12px; margin: 4px 0 0 0;">Pure Instant Coffee</p>
      </td>
    </tr>
    <tr>
      <td style="padding: 30px; color: #F5EED8; font-size: 15px; line-height: 1.7;">
        {safe}
      </td>
    </tr>
    <tr>
      <td style="padding: 15px 30px; border-top: 1px solid #333; text-align: center;">
        <p style="color: #888; font-size: 12px; margin: 0;">
          Purity Beans | p3online.in<br>
          <a href="https://p3online.in/unsubscribe" style="color: #888;">Unsubscribe</a>
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _log_nurture(
    lead_id: str, segment: str, stage: str,
    channel: str, result: dict,
) -> None:
    """Persist nurture send event to DB."""
    if not lead_id:
        return
    try:
        from content_generator.analytics.metrics_store import record_nurture_sent
        record_nurture_sent(
            lead_id=lead_id,
            segment=segment,
            stage=stage,
            channel=channel,
            success=result.get("success", False),
            message_id="",
        )
    except Exception as e:
        logger.debug("[email] Nurture log failed: %s", e)


# ── Batch dispatch ────────────────────────────────────────────────────────────

def dispatch_email_batch(
    leads: list[dict],
    dry_run: bool = False,
) -> list[dict]:
    """
    Dispatch email nurture sequences to a batch of leads.

    Each lead dict must have: lead_id, segment, stage, contact (email), name.

    dry_run=True logs what would be sent without making SMTP calls.
    """
    results = []
    for lead in leads:
        seg     = lead.get("segment", "consumer")
        stage   = lead.get("stage", "inquiry")
        contact = lead.get("contact", "")
        name    = lead.get("name", "")
        lead_id = lead.get("lead_id", "")

        # Only send email if contact looks like an email
        if "@" not in contact:
            continue

        if dry_run:
            logger.info(
                "[email] DRY RUN — would email %s (%s) | template=(%s, %s)",
                contact, lead_id, seg, stage,
            )
            results.append({"lead_id": lead_id, "success": True, "dry_run": True})
            continue

        result = send_email(
            to_email=contact,
            to_name=name,
            segment=seg,
            stage=stage,
            lead_id=lead_id,
        )
        results.append({"lead_id": lead_id, **result})

    return results
