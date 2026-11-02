from flask import Blueprint, render_template

from extensions import db
from models import Client, InventoryItem, Order, Product, Todo
from routes.auth import login_required
from routes.order_metrics import current_month, finance_totals, sold_coffee_weight

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    totals = finance_totals(current_month())

    individual_count = Client.query.filter_by(type="individual").count()
    b2b_count = Client.query.filter_by(type="b2b").count()
    products_count = Product.query.count()
    orders = Order.query.filter(
        db.or_(Order.source != "shop", Order.payment_status == "paid")
    ).all()
    orders_count = len(orders)
    total_kg, _ = sold_coffee_weight(orders, Product.query.all())
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
        total_kg=total_kg,
        individual_count=individual_count,
        b2b_count=b2b_count,
        products_count=products_count,
        orders_count=orders_count,
        inventory_count=inventory_count,
        todos=todos,
        todos_count=todos_count,
    )