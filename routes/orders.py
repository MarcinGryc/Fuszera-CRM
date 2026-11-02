from datetime import datetime
from math import isfinite

from flask import Blueprint, abort, redirect, render_template, request, url_for

from extensions import db
from models import Client, Finance, Order, OrderItem, Product
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
        if not (len(product_names) == len(unit_prices) == len(quantities)):
            abort(400, "Nieprawidłowe pozycje zamówienia.")

        parsed_items = []
        calculated_total = 0

        for name, price, quantity in zip(product_names, unit_prices, quantities):
            name = name.strip()
            if not name:
                continue

            try:
                price_float = float(price or 0)
                quantity_int = int(quantity or 1)
            except ValueError:
                abort(400, "Nieprawidłowa cena lub ilość produktu.")
            if (
                not isfinite(price_float)
                or price_float < 0
                or quantity_int < 1
                or quantity_int > 2_147_483_647
            ):
                abort(400, "Cena i ilość muszą być prawidłowe i nieujemne.")

            try:
                line_total = price_float * quantity_int
            except OverflowError:
                abort(400, "Wartość pozycji zamówienia jest zbyt duża.")
            if not isfinite(line_total):
                abort(400, "Wartość pozycji zamówienia jest zbyt duża.")
            calculated_total += line_total
            if not isfinite(calculated_total):
                abort(400, "Wartość zamówienia jest zbyt duża.")
            parsed_items.append((name, price_float, quantity_int, line_total))

        if not parsed_items:
            abort(400, "Dodaj co najmniej jedną pozycję do zamówienia.")

        total_input = request.form.get("total")
        try:
            order_total = float(total_input) if total_input else calculated_total
        except ValueError:
            abort(400, "Nieprawidłowa wartość zamówienia.")
        if not isfinite(order_total) or order_total < 0:
            abort(400, "Wartość zamówienia musi być prawidłowa i nieujemna.")

        order_date = request.form.get("order_date") or datetime.now().strftime("%Y-%m-%d")
        try:
            datetime.strptime(order_date, "%Y-%m-%d")
        except ValueError:
            abort(400, "Nieprawidłowa data zamówienia.")

        client_id = request.form.get("client_id") or None
        if client_id and not client_id.isdigit():
            abort(400, "Nieprawidłowy klient.")

        order = Order(
            client_id=int(client_id) if client_id else None,
            product_name=parsed_items[0][0],
            quantity=parsed_items[0][2],
            total=order_total,
            order_date=order_date,
            notes=request.form.get("notes"),
            source="manual",
            payment_status="manual",
        )
        db.session.add(order)
        db.session.flush()

        for name, price, quantity, line_total in parsed_items:
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    product_name=name,
                    unit_price=price,
                    quantity=quantity,
                    line_total=line_total,
                )
            )

        db.session.add(
            Finance(
                type="income",
                title=f"Zamówienie ręczne #{order.id}",
                amount=order.total,
                date=order.order_date,
            )
        )
        db.session.commit()
        return redirect(url_for("orders.orders"))

    q = request.args.get("q", "").strip()
    orders_query = Order.query

    if q:
        search = f"%{q}%"
        orders_query = orders_query.join(Client, Order.client_id == Client.id, isouter=True).filter(
            db.or_(
                Client.name.ilike(search),
                Client.company.ilike(search),
                Client.email.ilike(search),
                Client.phone.ilike(search),
                Order.notes.ilike(search),
            )
        )

    orders_list = orders_query.order_by(Order.order_date.desc(), Order.id.desc()).all()
    clients = Client.query.order_by(Client.name).all()
    products = Product.query.order_by(Product.name).all()

    return render_template("orders.html", orders=orders_list, clients=clients, products=products, q=q)


@orders_bp.route("/orders/delete/<int:order_id>", methods=["POST"])
@login_required
def order_delete(order_id):
    order = Order.query.get_or_404(order_id)
    if order.source == "shop":
        abort(409, "Zamówienia ze sklepu nie można usunąć z CRM.")
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