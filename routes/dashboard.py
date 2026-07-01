from flask import Blueprint, render_template
from sqlalchemy import func

from extensions import db
from models import Client, Finance, InventoryItem, Order, Product, Todo
from routes.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    income = (
        db.session.query(func.coalesce(func.sum(Finance.amount), 0))
        .filter(Finance.type == "income")
        .scalar()
    )

    expense = (
        db.session.query(func.coalesce(func.sum(Finance.amount), 0))
        .filter(Finance.type == "expense")
        .scalar()
    )

    balance = income - expense

    individual_count = Client.query.filter_by(type="individual").count()
    b2b_count = Client.query.filter_by(type="b2b").count()
    products_count = Product.query.count()
    orders_count = Order.query.count()
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
        income=income,
        expense=expense,
        balance=balance,
        individual_count=individual_count,
        b2b_count=b2b_count,
        products_count=products_count,
        orders_count=orders_count,
        inventory_count=inventory_count,
        todos=todos,
        todos_count=todos_count,
    )