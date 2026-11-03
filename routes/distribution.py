from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import func

from extensions import db
from models import DistributionContact
from routes.auth import login_required
from routes.distribution_contacts import LIST_TYPES, add_distribution_contact, distribution_lists, normalize_email
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
        email = normalize_email(request.form.get("email"))
        list_type = request.form.get("list_type")

        if not email or list_type not in LIST_TYPES:
            abort(400, "Podaj prawidłowy adres e-mail i listę.")
        add_distribution_contact(list_type, email)
        db.session.commit()

        return redirect(url_for("distribution.distribution"))

    return render_template("distribution.html", **distribution_lists())


@distribution_bp.route("/distribution/delete/<int:contact_id>", methods=["POST"])
@login_required
def distribution_delete(contact_id):
    contact = DistributionContact.query.get_or_404(contact_id)
    email = contact.email.strip().lower()
    DistributionContact.query.filter(
        DistributionContact.list_type == contact.list_type,
        func.lower(func.trim(DistributionContact.email)) == email,
    ).delete(synchronize_session=False)
    db.session.commit()
    return redirect(url_for("distribution.distribution"))


@distribution_bp.route("/distribution/export")
@login_required
def distribution_export():
    rows = [
        [
            contact["id"],
            "B2B" if list_type == "b2b" else "Indywidualni",
            contact["email"],
        ]
        for list_type, contacts in distribution_lists().items()
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
        email = normalize_email(row.get("Email"))

        if not email:
            continue

        add_distribution_contact("b2b" if "b2b" in raw_list else "individual", email)

    db.session.commit()
    return redirect(url_for("distribution.distribution"))
