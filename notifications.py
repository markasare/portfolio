from email.utils import formataddr
from html import escape

from flask import current_app
from flask_mail import Mail, Message

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


mail = Mail()


def init_notifications(app):
    mail.init_app(app)


def _sender_address(sender_email=None, sender_name="Mark Asare"):
    sender_email = sender_email or current_app.config.get("EMAIL_FROM") or current_app.config.get("MAIL_USERNAME")
    if not sender_email:
        return ""
    return formataddr((sender_name, sender_email))


def _ses_client_kwargs():
    client_kwargs = {"region_name": current_app.config.get("AWS_SES_REGION", "ap-southeast-2")}
    access_key = current_app.config.get("AWS_ACCESS_KEY_ID")
    secret_key = current_app.config.get("AWS_SECRET_ACCESS_KEY")
    session_token = current_app.config.get("AWS_SESSION_TOKEN")
    if access_key and secret_key:
        client_kwargs["aws_access_key_id"] = access_key
        client_kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            client_kwargs["aws_session_token"] = session_token
    return client_kwargs


def _send_via_ses(subject, recipient, text_body, html_body=None, reply_to=None, sender_email=None, sender_name="Mark Asare"):
    if boto3 is None:
        raise RuntimeError("boto3 is not installed.")

    client = boto3.client("ses", **_ses_client_kwargs())
    payload = {
        "Source": _sender_address(sender_email=sender_email, sender_name=sender_name),
        "Destination": {"ToAddresses": [recipient]},
        "Message": {
            "Subject": {"Data": subject},
            "Body": {
                "Text": {"Data": text_body},
                "Html": {"Data": html_body or text_body.replace("\n", "<br>")},
            },
        },
    }
    if reply_to:
        payload["ReplyToAddresses"] = [reply_to]
    client.send_email(**payload)
    return True


def _send_via_smtp(subject, recipient, text_body, html_body=None, reply_to=None, sender_email=None, sender_name="Mark Asare"):
    sender = _sender_address(sender_email=sender_email, sender_name=sender_name)
    if not sender or not current_app.config.get("MAIL_SERVER"):
        raise RuntimeError("SMTP is not configured.")

    message = Message(subject=subject, recipients=[recipient], body=text_body, html=html_body, sender=sender)
    if reply_to:
        message.reply_to = reply_to
    mail.send(message)
    return True


def send_email(subject, recipient, text_body, html_body=None, reply_to=None, sender_email=None, sender_name="Mark Asare"):
    provider = (current_app.config.get("EMAIL_PROVIDER") or "dev").lower()

    if provider == "ses":
        return _send_via_ses(subject, recipient, text_body, html_body=html_body, reply_to=reply_to, sender_email=sender_email, sender_name=sender_name)
    if provider in {"smtp", "mail"}:
        return _send_via_smtp(subject, recipient, text_body, html_body=html_body, reply_to=reply_to, sender_email=sender_email, sender_name=sender_name)
    if provider == "dev":
        current_app.logger.info("DEV email to %s\nSUBJECT: %s\n%s", recipient, subject, text_body)
        return True

    raise RuntimeError(f"Unsupported EMAIL_PROVIDER: {provider}")


def _format_message_html(message):
    return escape(message).replace("\n", "<br>")


def _email_shell(eyebrow, title, intro, body_html, note_html=None):
    note_section = ""
    if note_html:
        note_section = (
            "<div style=\"margin-top:24px;padding:16px 18px;border-radius:16px;"
            "background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.18);"
            "color:#b8c7d9;font-size:14px;line-height:1.7;\">"
            f"{note_html}"
            "</div>"
        )

    return (
        "<div style=\"margin:0;padding:32px 16px;background:#070b14;font-family:Inter,Arial,sans-serif;color:#e8f1fb;\">"
        "<div style=\"max-width:640px;margin:0 auto;border-radius:28px;overflow:hidden;"
        "background:#0b1324;border:1px solid rgba(148,163,184,0.16);box-shadow:0 24px 80px rgba(0,0,0,0.45);\">"
        "<div style=\"padding:32px;background:radial-gradient(circle at top right,rgba(6,214,255,0.20),transparent 35%),"
        "linear-gradient(135deg,#07111f 0%,#0d1b33 55%,#12365d 100%);color:#f8fbff;border-bottom:1px solid rgba(148,163,184,0.12);\">"
        f"<div style=\"display:inline-block;padding:7px 14px;border-radius:999px;background:rgba(6,214,255,0.08);border:1px solid rgba(6,214,255,0.22);font-size:11px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;color:#75e0ff;\">{eyebrow}</div>"
        f"<h1 style=\"margin:18px 0 0;font-size:36px;line-height:1.05;font-weight:800;font-family:Georgia,serif;color:#f4f9ff;\">{title}</h1>"
        "</div>"
        "<div style=\"padding:32px;background:linear-gradient(180deg,#0b1324 0%,#0a1120 100%);\">"
        f"<p style=\"margin:0 0 22px;font-size:16px;line-height:1.8;color:#b7c7db;\">{intro}</p>"
        f"{body_html}"
        f"{note_section}"
        "<div style=\"margin-top:28px;padding-top:18px;border-top:1px solid rgba(148,163,184,0.12);\">"
        "<p style=\"margin:0;font-size:14px;line-height:1.8;color:#89a0b8;\">Mark Asare</p>"
        "</div>"
        "</div>"
        "</div>"
        "</div>"
    )


def send_contact_emails(name, sender, message):
    owner_email = current_app.config.get("CONTACT_OWNER_EMAIL")
    auto_reply_enabled = current_app.config.get("ENABLE_AUTO_REPLY", True)
    if not owner_email and not auto_reply_enabled:
        raise RuntimeError("Set CONTACT_OWNER_EMAIL or enable auto replies.")

    safe_name = escape(name)
    safe_sender = escape(sender)
    safe_message = _format_message_html(message)

    if owner_email:
        owner_subject = f"Portfolio contact from {name}"
        owner_text = (
            f"New portfolio contact form submission\n\n"
            f"Name: {name}\n"
            f"Email: {sender}\n\n"
            f"Message:\n{message}\n"
        )
        owner_html = _email_shell(
            "Portfolio Contact",
            "New message received.",
            "A new message just came in through your portfolio contact form.",
            (
                "<div style=\"display:grid;gap:14px;\">"
                "<div style=\"padding:18px;border-radius:18px;background:rgba(255,255,255,0.03);border:1px solid rgba(148,163,184,0.14);\">"
                f"<div style=\"font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#7bdfff;margin-bottom:8px;\">From</div>"
                f"<div style=\"font-size:18px;font-weight:700;color:#f4f9ff;\">{safe_name}</div>"
                f"<div style=\"margin-top:4px;font-size:15px;color:#9fc1de;\">{safe_sender}</div>"
                "</div>"
                "<div style=\"padding:22px;border-radius:18px;background:linear-gradient(135deg,rgba(6,214,255,0.08),rgba(139,92,246,0.08));border:1px solid rgba(6,214,255,0.14);color:#ebf4ff;\">"
                "<div style=\"font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#75e0ff;margin-bottom:10px;\">Message</div>"
                f"<div style=\"font-size:15px;line-height:1.8;color:#dce8f5;\">{safe_message}</div>"
                "</div>"
                "</div>"
            ),
            note_html="Reply to this email to respond directly to the sender.",
        )
        send_email(owner_subject, owner_email, owner_text, html_body=owner_html, reply_to=sender)

    if auto_reply_enabled:
        auto_subject = "Thanks for reaching out to Mark Asare"
        auto_text = (
            f"Hi {name},\n\n"
            "Thanks for reaching out through markasare.com. Your message has been received and will be attended to shortly. "
            "Someone may contact you if more context is needed.\n\n"
            "This mailbox is not monitored, so please do not reply to this email.\n\n"
            f"Original message:\n{message}\n"
        )
        auto_html = _email_shell(
            "Message Received",
            "Thanks for reaching out.",
            f"Hi {safe_name}, thanks for getting in touch. Your message has been received and will be attended to shortly.",
            (
                "<div style=\"padding:22px;border-radius:18px;background:linear-gradient(135deg,rgba(255,255,255,0.03) 0%,rgba(6,214,255,0.08) 100%);"
                "border:1px solid rgba(6,214,255,0.14);\">"
                "<div style=\"font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#7bdfff;margin-bottom:10px;\">Your message</div>"
                f"<div style=\"font-size:15px;line-height:1.8;color:#dce8f5;\">{safe_message}</div>"
                "</div>"
            ),
            note_html="This mailbox is not monitored, so please do not reply to this email. If more context is needed, someone may contact you directly.",
        )
        send_email(auto_subject, sender, auto_text, html_body=auto_html, sender_email=current_app.config.get("EMAIL_FROM"), sender_name="Mark Asare")


def explain_delivery_error(exc):
    if isinstance(exc, ClientError):
        error_message = exc.response.get("Error", {}).get("Message", str(exc))
        if "Email address is not verified" in error_message:
            return (
                "SES rejected the message because an email identity is not verified. Verify EMAIL_FROM in SES. "
                "If the SES account is still in sandbox, every recipient must also be verified or ENABLE_AUTO_REPLY must be false."
            )
        return error_message
    return str(exc)