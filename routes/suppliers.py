from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import Supplier
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

suppliers_bp = Blueprint("suppliers", __name__)


def clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@suppliers_bp.route("/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    if request.method == "POST":
        supplier = Supplier(
            name=request.form.get("name"),
            supplies=request.form.get("supplies"),
            email=request.form.get("email"),
            phone=request.form.get("phone"),
            nip=request.form.get("nip"),
            address=request.form.get("address"),
        )
        db.session.add(supplier)
        db.session.commit()
        return redirect(url_for("suppliers.suppliers"))

    q = request.args.get("q", "").strip()
    query = Supplier.query

    if q:
        search = f"%{q}%"
        query = query.filter(
            db.or_(
                Supplier.name.ilike(search),
                Supplier.supplies.ilike(search),
                Supplier.email.ilike(search),
                Supplier.phone.ilike(search),
                Supplier.nip.ilike(search),
                Supplier.address.ilike(search),
            )
        )

    suppliers_list = query.order_by(Supplier.name).all()
    return render_template("suppliers.html", suppliers=suppliers_list, q=q)


@suppliers_bp.route("/suppliers/edit/<int:supplier_id>", methods=["GET", "POST"])
@login_required
def supplier_edit(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        supplier.name = request.form.get("name")
        supplier.supplies = request.form.get("supplies")
        supplier.email = request.form.get("email")
        supplier.phone = request.form.get("phone")
        supplier.nip = request.form.get("nip")
        supplier.address = request.form.get("address")
        db.session.commit()
        return redirect(url_for("suppliers.suppliers"))

    return render_template("supplier_edit.html", supplier=supplier)


@suppliers_bp.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
@login_required
def supplier_delete(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    db.session.delete(supplier)
    db.session.commit()
    return redirect(url_for("suppliers.suppliers"))


@suppliers_bp.route("/suppliers/export")
@login_required
def suppliers_export():
    suppliers = Supplier.query.order_by(Supplier.name).all()

    rows = [
        [s.id, s.name, s.supplies, s.email, s.phone, s.nip, s.address]
        for s in suppliers
    ]

    return export_xlsx(
        "dostawcy.xlsx",
        [("Dostawcy", ["ID", "Nazwa", "Co dostarcza", "Email", "Telefon", "NIP", "Adres"], rows)],
    )


@suppliers_bp.route("/suppliers/import", methods=["POST"])
@login_required
def suppliers_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("suppliers.suppliers"))

    rows = read_xlsx_rows(file)

    for row in rows:
        supplier = Supplier(
            name=clean(row.get("Nazwa")) or "Bez nazwy",
            supplies=clean(row.get("Co dostarcza")),
            email=clean(row.get("Email")),
            phone=clean(row.get("Telefon")),
            nip=clean(row.get("NIP")),
            address=clean(row.get("Adres")),
        )
        db.session.add(supplier)

    db.session.commit()
    return redirect(url_for("suppliers.suppliers"))