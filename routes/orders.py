from datetime import datetime

from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import Client, Order, OrderItem, Product
from routes.auth import login_required
from routes.export_utils import export_xlsx

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("/orders", methods=["GET", "POST"])
@login_required
def orders():
    if request.method == "POST":
        product_names = request.form.getlist("product_name")
        unit_prices = request.form.getlist("unit_price")
        quantities = request.form.getlist("quantity")

        order = Order(
            client_id=request.form.get("client_id") or None,
            total=float(request.form.get("total") or 0),
            order_date=request.form.get("order_date") or datetime.now().strftime("%Y-%m-%d"),
            notes=request.form.get("notes"),
        )

        db.session.add(order)
        db.session.flush()

        calculated_total = 0

        for name, price, quantity in zip(product_names, unit_prices, quantities):
            if not name:
                continue

            price_float = float(price or 0)
            quantity_int = int(quantity or 1)
            line_total = price_float * quantity_int
            calculated_total += line_total

            item = OrderItem(
                order_id=order.id,
                product_name=name,
                unit_price=price_float,
                quantity=quantity_int,
                line_total=line_total,
            )
            db.session.add(item)

        if not request.form.get("total"):
            order.total = calculated_total

        db.session.commit()
        return redirect(url_for("orders.orders"))

    orders_list = Order.query.order_by(Order.order_date.desc(), Order.id.desc()).all()
    clients = Client.query.order_by(Client.name).all()
    products = Product.query.order_by(Product.name).all()

    return render_template("orders.html", orders=orders_list, clients=clients, products=products)


@orders_bp.route("/orders/delete/<int:order_id>", methods=["POST"])
@login_required
def order_delete(order_id):
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for("orders.orders"))


@orders_bp.route("/orders/export")
@login_required
def orders_export():
    orders = Order.query.order_by(Order.order_date.desc(), Order.id.desc()).all()

    order_rows = []
    item_rows = []

    for order in orders:
        order_rows.append([
            order.id,
            order.order_date,
            order.client.company if order.client and order.client.company else (order.client.name if order.client else "Brak"),
            order.total,
            order.notes,
        ])

        for item in order.items:
            item_rows.append([
                order.id,
                order.order_date,
                item.product_name,
                item.unit_price,
                item.quantity,
                item.line_total,
            ])

    return export_xlsx(
        "zamowienia.xlsx",
        [
            ("Zamówienia", ["ID", "Data", "Klient", "Wartość", "Notatki"], order_rows),
            ("Pozycje", ["ID zamówienia", "Data", "Produkt", "Cena jedn.", "Ilość", "Suma"], item_rows),
        ],
    )