from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import InventoryItem
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():
    if request.method == "POST":
        item = InventoryItem(
            name=request.form.get("name"),
            quantity=float(request.form.get("quantity") or 0),
            unit=request.form.get("unit") or "szt",
            notes=request.form.get("notes"),
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for("inventory.inventory"))

    q = request.args.get("q", "").strip()
    query = InventoryItem.query

    if q:
        search = f"%{q}%"
        query = query.filter(
            db.or_(
                InventoryItem.name.ilike(search),
                InventoryItem.unit.ilike(search),
                InventoryItem.notes.ilike(search),
            )
        )

    items = query.order_by(InventoryItem.name).all()
    return render_template("inventory.html", items=items, q=q)


@inventory_bp.route("/inventory/update/<int:item_id>", methods=["POST"])
@login_required
def inventory_update(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    item.quantity = float(request.form.get("quantity") or 0)
    db.session.commit()
    return redirect(url_for("inventory.inventory"))


@inventory_bp.route("/inventory/delete/<int:item_id>", methods=["POST"])
@login_required
def inventory_delete(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("inventory.inventory"))


@inventory_bp.route("/inventory/export")
@login_required
def inventory_export():
    items = InventoryItem.query.order_by(InventoryItem.name).all()
    rows = [[i.id, i.name, i.quantity, i.unit, i.notes] for i in items]

    return export_xlsx(
        "magazyn.xlsx",
        [("Magazyn", ["ID", "Nazwa", "Stan", "Jednostka", "Notatki"], rows)],
    )


@inventory_bp.route("/inventory/import", methods=["POST"])
@login_required
def inventory_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("inventory.inventory"))

    rows = read_xlsx_rows(file)

    for row in rows:
        item = InventoryItem(
            name=row.get("Nazwa") or "Bez nazwy",
            quantity=float(row.get("Stan") or 0),
            unit=row.get("Jednostka") or "szt",
            notes=row.get("Notatki"),
        )
        db.session.add(item)

    db.session.commit()
    return redirect(url_for("inventory.inventory"))