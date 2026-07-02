from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import DistributionContact
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

distribution_bp = Blueprint("distribution", __name__)


def clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@distribution_bp.route("/distribution", methods=["GET", "POST"])
@login_required
def distribution():
    if request.method == "POST":
        email = clean(request.form.get("email")).lower()
        list_type = request.form.get("list_type")

        if email:
            contact = DistributionContact(
                list_type=list_type,
                email=email,
            )
            db.session.add(contact)
            db.session.commit()

        return redirect(url_for("distribution.distribution"))

    b2b = DistributionContact.query.filter_by(list_type="b2b").order_by(DistributionContact.email).all()
    individual = DistributionContact.query.filter_by(list_type="individual").order_by(DistributionContact.email).all()

    return render_template("distribution.html", b2b=b2b, individual=individual)


@distribution_bp.route("/distribution/delete/<int:contact_id>", methods=["POST"])
@login_required
def distribution_delete(contact_id):
    contact = DistributionContact.query.get_or_404(contact_id)
    db.session.delete(contact)
    db.session.commit()
    return redirect(url_for("distribution.distribution"))


@distribution_bp.route("/distribution/export")
@login_required
def distribution_export():
    contacts = DistributionContact.query.order_by(
        DistributionContact.list_type,
        DistributionContact.email
    ).all()

    rows = [
        [
            contact.id,
            "B2B" if contact.list_type == "b2b" else "Indywidualni",
            contact.email,
        ]
        for contact in contacts
    ]

    return export_xlsx(
        "listy_dystrybucyjne.xlsx",
        [
            (
                "Listy",
                ["ID", "Lista", "Email"],
                rows,
            )
        ],
    )


@distribution_bp.route("/distribution/import", methods=["POST"])
@login_required
def distribution_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("distribution.distribution"))

    rows = read_xlsx_rows(file)

    for row in rows:
        raw_list = clean(row.get("Lista")).lower()
        email = clean(row.get("Email")).lower()

        if not email:
            continue

        contact = DistributionContact(
            list_type="b2b" if "b2b" in raw_list else "individual",
            email=email,
        )

        db.session.add(contact)

    db.session.commit()
    return redirect(url_for("distribution.distribution"))