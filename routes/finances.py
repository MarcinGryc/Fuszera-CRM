from datetime import datetime

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import func

from extensions import db
from models import Finance
from routes.auth import login_required
from routes.export_utils import export_xlsx

finances_bp = Blueprint("finances", __name__)


@finances_bp.route("/finances", methods=["GET", "POST"])
@login_required
def finances():
    if request.method == "POST":
        item = Finance(
            type=request.form.get("type"),
            title=request.form.get("title"),
            amount=float(request.form.get("amount") or 0),
            date=request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for("finances.finances"))

    items = Finance.query.order_by(Finance.date.desc(), Finance.id.desc()).all()

    income = db.session.query(func.coalesce(func.sum(Finance.amount), 0)).filter(Finance.type == "income").scalar()
    expense = db.session.query(func.coalesce(func.sum(Finance.amount), 0)).filter(Finance.type == "expense").scalar()
    balance = income - expense

    return render_template("finances.html", items=items, income=income, expense=expense, balance=balance)


@finances_bp.route("/finances/delete/<int:item_id>", methods=["POST"])
@login_required
def finance_delete(item_id):
    item = Finance.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("finances.finances"))


@finances_bp.route("/finances/export")
@login_required
def finances_export():
    items = Finance.query.order_by(Finance.date.desc(), Finance.id.desc()).all()

    rows = [
        [
            i.id,
            i.date,
            "Przychód" if i.type == "income" else "Wydatek",
            i.title,
            i.amount,
        ]
        for i in items
    ]

    return export_xlsx(
        "finanse.xlsx",
        [("Finanse", ["ID", "Data", "Typ", "Tytuł", "Kwota"], rows)],
    )