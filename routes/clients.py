from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import Client
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

clients_bp = Blueprint("clients", __name__)


def clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@clients_bp.route("/clients", methods=["GET", "POST"])
@login_required
def clients():
    if request.method == "POST":
        client = Client(
            type=request.form.get("type"),
            name=request.form.get("name"),
            company=request.form.get("company"),
            nip=request.form.get("nip"),
            email=request.form.get("email"),
            phone=request.form.get("phone"),
            address=request.form.get("address"),
            notes=request.form.get("notes"),
        )
        db.session.add(client)
        db.session.commit()
        return redirect(url_for("clients.clients"))

    q = request.args.get("q", "").strip()
    query = Client.query

    if q:
        search = f"%{q}%"
        query = query.filter(
            db.or_(
                Client.name.ilike(search),
                Client.company.ilike(search),
                Client.email.ilike(search),
                Client.phone.ilike(search),
                Client.nip.ilike(search),
                Client.address.ilike(search),
            )
        )

    b2b = query.filter_by(type="b2b").order_by(Client.id.desc()).all()
    individual = query.filter_by(type="individual").order_by(Client.id.desc()).all()

    return render_template("clients.html", b2b=b2b, individual=individual, q=q)


@clients_bp.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    orders = sorted(client.orders, key=lambda order: (order.order_date, order.id), reverse=True)
    return render_template("client_detail.html", client=client, orders=orders)


@clients_bp.route("/clients/edit/<int:client_id>", methods=["GET", "POST"])
@login_required
def client_edit(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == "POST":
        client.type = request.form.get("type")
        client.name = request.form.get("name")
        client.company = request.form.get("company")
        client.nip = request.form.get("nip")
        client.email = request.form.get("email")
        client.phone = request.form.get("phone")
        client.address = request.form.get("address")
        client.notes = request.form.get("notes")
        db.session.commit()
        return redirect(url_for("clients.clients"))

    return render_template("client_edit.html", client=client)


@clients_bp.route("/clients/delete/<int:client_id>", methods=["POST"])
@login_required
def client_delete(client_id):
    client = Client.query.get_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    return redirect(url_for("clients.clients"))


@clients_bp.route("/clients/export")
@login_required
def clients_export():
    clients = Client.query.order_by(Client.type, Client.name).all()

    rows = [
        [
            c.id,
            "B2B" if c.type == "b2b" else "Indywidualny",
            c.name,
            c.company,
            c.nip,
            c.email,
            c.phone,
            c.address,
            c.notes,
        ]
        for c in clients
    ]

    return export_xlsx(
        "klienci.xlsx",
        [("Klienci", ["ID", "Typ", "Nazwa/osoba", "Firma", "NIP", "Email", "Telefon", "Adres", "Notatki"], rows)],
    )


@clients_bp.route("/clients/import", methods=["POST"])
@login_required
def clients_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("clients.clients"))

    rows = read_xlsx_rows(file)

    for row in rows:
        raw_type = clean(row.get("Typ")).lower()
        client_type = "b2b" if raw_type == "b2b" else "individual"

        name = (
            clean(row.get("Nazwa/osoba"))
            or clean(row.get("Nazwa"))
            or clean(row.get("Imię i nazwisko"))
            or clean(row.get("Osoba"))
            or clean(row.get("Firma"))
            or "Brak nazwy"
        )

        client = Client(
            type=client_type,
            name=name,
            company=clean(row.get("Firma")),
            nip=clean(row.get("NIP")),
            email=clean(row.get("Email")),
            phone=clean(row.get("Telefon")),
            address=clean(row.get("Adres")),
            notes=clean(row.get("Notatki")),
        )

        db.session.add(client)

    db.session.commit()
    return redirect(url_for("clients.clients"))