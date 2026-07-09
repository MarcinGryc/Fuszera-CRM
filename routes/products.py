from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import Product
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

products_bp = Blueprint("products", __name__)


@products_bp.route("/products", methods=["GET", "POST"])
@login_required
def products():
    if request.method == "POST":
        product = Product(
            name=request.form.get("name"),
            weight=request.form.get("weight"),
            price=float(request.form.get("price") or 0),
        )
        db.session.add(product)
        db.session.commit()
        return redirect(url_for("products.products"))

    q = request.args.get("q", "").strip()
    query = Product.query

    if q:
        search = f"%{q}%"
        query = query.filter(
            db.or_(
                Product.name.ilike(search),
                Product.weight.ilike(search),
            )
        )

    products_list = query.order_by(Product.id.desc()).all()
    return render_template("products.html", products=products_list, q=q)


@products_bp.route("/products/delete/<int:product_id>", methods=["POST"])
@login_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for("products.products"))


@products_bp.route("/products/export")
@login_required
def products_export():
    products = Product.query.order_by(Product.name).all()
    rows = [[p.id, p.name, p.weight, p.price] for p in products]

    return export_xlsx(
        "produkty.xlsx",
        [("Produkty", ["ID", "Nazwa", "Gramatura", "Cena"], rows)],
    )


@products_bp.route("/products/import", methods=["POST"])
@login_required
def products_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("products.products"))

    rows = read_xlsx_rows(file)

    for row in rows:
        product = Product(
            name=row.get("Nazwa") or row.get("Produkt") or "Bez nazwy",
            weight=row.get("Gramatura"),
            price=float(row.get("Cena") or 0),
        )
        db.session.add(product)

    db.session.commit()
    return redirect(url_for("products.products"))