from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import Supplier
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

suppliers_bp = Blueprint("suppliers", __name__)


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

    suppliers_list = Supplier.query.order_by(Supplier.name).all()
    return render_template("suppliers.html", suppliers=suppliers_list)


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
            name=row.get("Nazwa") or "Bez nazwy",
            supplies=row.get("Co dostarcza"),
            email=row.get("Email"),
            phone=row.get("Telefon"),
            nip=row.get("NIP"),
            address=row.get("Adres"),
        )

        db.session.add(supplier)

    db.session.commit()

    return redirect(url_for("suppliers.suppliers"))