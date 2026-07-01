from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import InventoryItem
from routes.auth import login_required
from routes.export_utils import export_xlsx

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

    items = InventoryItem.query.order_by(InventoryItem.name).all()
    return render_template("inventory.html", items=items)


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