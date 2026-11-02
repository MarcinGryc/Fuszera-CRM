from flask import Blueprint, render_template, request

from extensions import db
from models import Client, InventoryItem, Order, Product, Todo
from routes.auth import login_required
from routes.order_metrics import finance_totals, selected_month, sold_coffee_weight

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    month = selected_month(request.args.get("month"))
    totals = finance_totals(month)

    individual_count = Client.query.filter_by(type="individual").count()
    b2b_count = Client.query.filter_by(type="b2b").count()
    products_count = Product.query.count()
    orders = Order.query.filter(
        db.or_(Order.source != "shop", Order.payment_status == "paid")
    ).all()
    orders_count = len(orders)
    total_kg, month_kg = sold_coffee_weight(orders, Product.query.all(), month)
    inventory_count = InventoryItem.query.count()

    todos = (
        Todo.query
        .filter_by(done=False)
        .order_by(Todo.id.desc())
        .limit(8)
        .all()
    )

    todos_count = Todo.query.filter_by(done=False).count()

    return render_template(
        "index.html",
        **totals,
        selected_month=month,
        total_kg=total_kg,
        month_kg=month_kg,
        individual_count=individual_count,
        b2b_count=b2b_count,
        products_count=products_count,
        orders_count=orders_count,
        inventory_count=inventory_count,
        todos=todos,
        todos_count=todos_count,
    )