import os
import smtplib
from email.message import EmailMessage

from flask import Blueprint, redirect, render_template, request, url_for

from models import DistributionContact
from routes.auth import login_required

offers_bp = Blueprint("offers", __name__)


def send_offer_email(subject, body, recipients, mode):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)
    smtp_from_name = os.environ.get("SMTP_FROM_NAME", "Fuszera")

    if not all([smtp_host, smtp_user, smtp_password, smtp_from]):
        raise RuntimeError("Brakuje konfiguracji SMTP w zmiennych środowiskowych.")

    if mode == "bcc":
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{smtp_from_name} <{smtp_from}>"
        msg["To"] = smtp_from
        msg["Bcc"] = ", ".join(recipients)
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)

            for recipient in recipients:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = f"{smtp_from_name} <{smtp_from}>"
                msg["To"] = recipient
                msg.set_content(body)
                server.send_message(msg)


@offers_bp.route("/offers", methods=["GET", "POST"])
@login_required
def offers():
    message = None
    error = None

    if request.method == "POST":
        list_type = request.form.get("list_type")
        subject = request.form.get("subject")
        body = request.form.get("body")
        mode = request.form.get("mode")

        contacts = DistributionContact.query.filter_by(list_type=list_type).all()
        recipients = sorted({contact.email for contact in contacts if contact.email})

        try:
            if not recipients:
                raise RuntimeError("Wybrana lista jest pusta.")

            send_offer_email(subject, body, recipients, mode)
            message = f"Wysłano ofertę do {len(recipients)} adresów."

        except Exception as e:
            error = str(e)

    individual_count = DistributionContact.query.filter_by(list_type="individual").count()
    b2b_count = DistributionContact.query.filter_by(list_type="b2b").count()

    return render_template(
        "offers.html",
        message=message,
        error=error,
        individual_count=individual_count,
        b2b_count=b2b_count,
    )