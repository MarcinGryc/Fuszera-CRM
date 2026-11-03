import json
import os
import smtplib
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from email.message import EmailMessage

from flask import Blueprint, current_app, render_template, request

from extensions import db
from routes.auth import login_required
from routes.distribution_contacts import distribution_lists

offers_bp = Blueprint("offers", __name__)


def get_smtp_config():
    cfg = {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "security": os.environ.get("SMTP_SECURITY", "starttls").lower(),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "from_email": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER"),
        "from_name": os.environ.get("SMTP_FROM_NAME", "Fuszera Coffee"),
    }
    if cfg["security"] not in {"ssl", "starttls", "none"}:
        raise RuntimeError("SMTP_SECURITY musi mieć wartość ssl, starttls albo none.")
    return cfg


def get_resend_config():
    return {
        "api_key": os.environ.get("RESEND_API_KEY"),
        "from_email": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER"),
        "from_name": os.environ.get("SMTP_FROM_NAME", "Fuszera Coffee"),
    }


def get_email_provider():
    provider = os.environ.get("EMAIL_PROVIDER", "smtp").lower()
    if provider not in {"smtp", "resend"}:
        raise RuntimeError("EMAIL_PROVIDER musi mieć wartość smtp albo resend.")
    return provider


def resend_request(cfg, method, path, payload=None):
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = Request(
        f"https://api.resend.com{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(req, timeout=30) as response:
            return response.status
    except HTTPError as error:
        raise RuntimeError(f"Resend API zwróciło błąd HTTP {error.code}.") from error


def smtp_connect(cfg, timeout=30):
    if cfg["security"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=timeout)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=timeout)
        server.ehlo()
        if cfg["security"] == "starttls":
            server.starttls()
            server.ehlo()

    server.login(cfg["user"], cfg["password"])
    return server


def test_smtp_connection():
    cfg = get_smtp_config()

    if not all([cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["from_email"]]):
        raise RuntimeError("Brakuje konfiguracji SMTP w zmiennych środowiskowych.")

    try:
        with smtp_connect(cfg, timeout=30) as server:
            server.noop()

    except Exception as e:
        raise RuntimeError(f"SMTP TEST ERROR: {repr(e)}")


def test_email_connection():
    if get_email_provider() == "smtp":
        test_smtp_connection()
        return

    cfg = get_resend_config()
    if not cfg["api_key"] or not cfg["from_email"]:
        raise RuntimeError("Brakuje RESEND_API_KEY lub SMTP_FROM.")
    resend_request(cfg, "GET", "/domains")


def send_offer_email(subject, body, recipients, mode):
    if mode not in {"bcc", "separate"}:
        raise RuntimeError("Nieprawidłowy sposób wysyłki.")

    if get_email_provider() == "resend":
        cfg = get_resend_config()
        if not cfg["api_key"] or not cfg["from_email"]:
            raise RuntimeError("Brakuje RESEND_API_KEY lub SMTP_FROM.")
        sender = f"{cfg['from_name']} <{cfg['from_email']}>"

        if mode == "bcc":
            for start in range(0, len(recipients), 49):
                resend_request(
                    cfg,
                    "POST",
                    "/emails",
                    {
                        "from": sender,
                        "to": [cfg["from_email"]],
                        "bcc": recipients[start : start + 49],
                        "subject": subject,
                        "text": body,
                    },
                )
        else:
            for recipient in recipients:
                resend_request(
                    cfg,
                    "POST",
                    "/emails",
                    {
                        "from": sender,
                        "to": [recipient],
                        "subject": subject,
                        "text": body,
                    },
                )
        return

    cfg = get_smtp_config()

    if not all([cfg["host"], cfg["port"], cfg["user"], cfg["password"], cfg["from_email"]]):
        raise RuntimeError("Brakuje konfiguracji SMTP w zmiennych środowiskowych.")

    with smtp_connect(cfg, timeout=60) as server:
        if mode == "bcc":
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = cfg["from_email"]
            msg["Bcc"] = ", ".join(recipients)
            msg.set_content(body)
            server.send_message(msg)

        else:
            for recipient in recipients:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
                msg["To"] = recipient
                msg.set_content(body)
                server.send_message(msg)


@offers_bp.route("/offers", methods=["GET", "POST"])
@login_required
def offers():
    if not current_app.config.get("OFFERS_ENABLED", False):
        return render_template("offers.html", offers_enabled=False), (
            409 if request.method == "POST" else 200
        )

    message = None
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        try:
            if action == "test_smtp":
                test_email_connection()
                message = "Połączenie z dostawcą poczty działa poprawnie."

            elif action == "send_offer":
                list_type = request.form.get("list_type")
                subject = request.form.get("subject")
                body = request.form.get("body")
                mode = request.form.get("mode")

                recipients = [contact["email"] for contact in distribution_lists().get(list_type, [])]

                if not recipients:
                    raise RuntimeError("Wybrana lista jest pusta.")

                db.session.close()

                send_offer_email(subject, body, recipients, mode)
                message = f"Wysłano ofertę do {len(recipients)} adresów."

        except Exception as e:
            error = str(e)

    lists = distribution_lists()

    return render_template(
        "offers.html",
        offers_enabled=True,
        message=message,
        error=error,
        individual_count=len(lists["individual"]),
        b2b_count=len(lists["b2b"]),
    )
