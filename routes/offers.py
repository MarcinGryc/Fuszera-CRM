import os
import smtplib
import socket
from email.message import EmailMessage

from flask import Blueprint, render_template, request
from sqlalchemy import select

from extensions import db
from models import DistributionContact
from routes.auth import login_required

offers_bp = Blueprint("offers", __name__)


def get_smtp_config():
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "security": os.environ.get("SMTP_SECURITY", "starttls").lower(),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "from_email": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER"),
        "from_name": os.environ.get("SMTP_FROM_NAME", "Fuszera Coffee"),
    }


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
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.noop()

    except Exception as e:
        raise RuntimeError(f"SMTP TEST ERROR: {repr(e)}")


def send_offer_email(subject, body, recipients, mode):
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
    message = None
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        try:
            if action == "test_smtp":
                test_smtp_connection()
                message = "Połączenie SMTP działa poprawnie."

            elif action == "send_offer":
                list_type = request.form.get("list_type")
                subject = request.form.get("subject")
                body = request.form.get("body")
                mode = request.form.get("mode")

                recipients = db.session.execute(
                    select(DistributionContact.email).where(
                        DistributionContact.list_type == list_type
                    )
                ).scalars().all()

                recipients = sorted({email.strip() for email in recipients if email and "@" in email})

                if not recipients:
                    raise RuntimeError("Wybrana lista jest pusta.")

                db.session.close()

                send_offer_email(subject, body, recipients, mode)
                message = f"Wysłano ofertę do {len(recipients)} adresów."

        except Exception as e:
            error = str(e)

    individual_count = db.session.execute(
        select(db.func.count()).select_from(DistributionContact).where(
            DistributionContact.list_type == "individual"
        )
    ).scalar()

    b2b_count = db.session.execute(
        select(db.func.count()).select_from(DistributionContact).where(
            DistributionContact.list_type == "b2b"
        )
    ).scalar()

    return render_template(
        "offers.html",
        message=message,
        error=error,
        individual_count=individual_count,
        b2b_count=b2b_count,
    )