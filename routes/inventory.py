from math import isfinite

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from extensions import db
from inventory_setup import CATEGORIES, CATEGORY_KEYS, DEFAULT_UNITS
from models import InventoryItem, Product
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

inventory_bp = Blueprint("inventory", __name__)

CATEGORY_LABELS = {key: label for key, label, _ in CATEGORIES}


def _number(value, default=0.0):
    try:
        number = float(str(value).replace(",", ".")) if value not in (None, "") else default
    except ValueError:
        abort(400, "Podaj prawidłową liczbę.")
    if not isfinite(number):
        abort(400, "Podaj prawidłową liczbę.")
    return number


def _category(value):
    value = (value or "").strip()
    if value in CATEGORY_KEYS:
        return value
    by_label = {label.casefold(): key for key, label in CATEGORY_LABELS.items()}
    return by_label.get(value.casefold())


def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def _next_position(category):
    last = db.session.query(db.func.max(InventoryItem.sort_order)).filter(InventoryItem.category == category).scalar()
    return (last if last is not None else -1) + 1


@inventory_bp.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        category = _category(request.form.get("category"))
        if not name or not category:
            abort(400, "Podaj nazwę i kategorię.")
        item = InventoryItem(
            name=name,
            quantity=_number(request.form.get("quantity")),
            unit=(request.form.get("unit") or "").strip() or DEFAULT_UNITS[category],
            category=category,
            sort_order=_next_position(category),
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for("inventory.inventory", _anchor=f"kat-{category}"))

    items = InventoryItem.query.order_by(InventoryItem.sort_order, InventoryItem.id).all()
    sections = [
        {"key": key, "label": label, "unit": unit, "items": [item for item in items if item.category == key]}
        for key, label, unit in CATEGORIES
    ]
    other = [item for item in items if item.category not in CATEGORY_KEYS]
    products = Product.query.order_by(Product.name).all()
    return render_template(
        "inventory.html", sections=sections, other=other, products=products,
        categories=CATEGORIES, default_units=DEFAULT_UNITS,
    )


@inventory_bp.route("/inventory/update/<int:item_id>", methods=["POST"])
@login_required
def inventory_update(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    if "name" in request.form:
        name = request.form.get("name", "").strip()
        if not name:
            abort(400, "Nazwa nie może być pusta.")
        item.name = name
    if "quantity" in request.form:
        item.quantity = _number(request.form.get("quantity"))
    if "unit" in request.form:
        item.unit = request.form.get("unit", "").strip() or DEFAULT_UNITS.get(item.category, "szt")
    if "category" in request.form:
        category = _category(request.form.get("category"))
        if not category:
            abort(400, "Nieznana kategoria.")
        if category != item.category:
            item.category = category
            item.sort_order = _next_position(category)
    db.session.commit()
    if _wants_json():
        return "", 204
    return redirect(url_for("inventory.inventory", _anchor=f"kat-{item.category}"))


@inventory_bp.route("/inventory/reorder", methods=["POST"])
@login_required
def inventory_reorder():
    data = request.get_json(silent=True) or {}
    category = data.get("category")
    ids = data.get("ids")
    if category not in CATEGORY_KEYS or not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        abort(400, "Nieprawidłowa kolejność.")
    items = {item.id: item for item in InventoryItem.query.filter_by(category=category).all()}
    if set(ids) != set(items):
        abort(409, "Lista pozycji się zmieniła. Odśwież stronę.")
    for position, item_id in enumerate(ids):
        items[item_id].sort_order = position
    db.session.commit()
    return jsonify(ok=True)


@inventory_bp.route("/inventory/delete/<int:item_id>", methods=["POST"])
@login_required
def inventory_delete(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    category = item.category
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("inventory.inventory", _anchor=f"kat-{category}" if category in CATEGORY_KEYS else None))


@inventory_bp.route("/inventory/export")
@login_required
def inventory_export():
    items = InventoryItem.query.order_by(InventoryItem.category, InventoryItem.sort_order, InventoryItem.id).all()
    rows = [[i.id, CATEGORY_LABELS.get(i.category, ""), i.name, i.quantity, i.unit, i.notes] for i in items]

    return export_xlsx(
        "magazyn.xlsx",
        [("Magazyn", ["ID", "Kategoria", "Nazwa", "Stan", "Jednostka", "Notatki"], rows)],
    )


@inventory_bp.route("/inventory/import", methods=["POST"])
@login_required
def inventory_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("inventory.inventory"))

    rows = read_xlsx_rows(file)

    for row in rows:
        category = _category(str(row.get("Kategoria") or ""))
        item = InventoryItem(
            name=row.get("Nazwa") or "Bez nazwy",
            quantity=_number(row.get("Stan")),
            unit=row.get("Jednostka") or DEFAULT_UNITS.get(category, "szt"),
            notes=row.get("Notatki"),
            category=category,
            sort_order=_next_position(category) if category else 0,
        )
        db.session.add(item)
        db.session.flush()

    db.session.commit()
    return redirect(url_for("inventory.inventory"))
