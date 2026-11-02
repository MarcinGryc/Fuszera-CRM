import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import abort
from sqlalchemy import func

from models import Finance, Product


WEIGHT_PATTERN = re.compile(
    r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(kg|kilograms?|g|grams?)\b",
    re.IGNORECASE,
)


def current_month():
    return datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m")


def previous_month():
    first_of_month = datetime.now(ZoneInfo("Europe/Warsaw")).replace(day=1)
    return (first_of_month - timedelta(days=1)).strftime("%Y-%m")


def selected_month(value):
    if value is None:
        return previous_month()
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        abort(400, "Wybierz prawidłowy miesiąc.")


def weight_in_kg(value):
    if not value:
        return 0
    match = WEIGHT_PATTERN.search(value)
    if not match:
        return 0
    amount = float(match.group(1).replace(",", "."))
    return amount if match.group(2).lower().startswith(("kg", "kilo")) else amount / 1000


def sold_coffee_weight(orders, products, month=None):
    products_by_name = {
        product.name.casefold(): product
        for product in products
        if product.name
    }
    shop_paid_dates = {
        item.source_ref.removeprefix("shop:"): item.date
        for item in Finance.query.filter(
            Finance.type == "income",
            Finance.source_ref.isnot(None),
            Finance.source_ref.like("shop:%"),
        ).all()
    }
    total_kg = 0
    month_kg = 0

    for order in orders:
        if order.source == "shop" and order.payment_status != "paid":
            continue

        paid_date = (
            shop_paid_dates.get(order.external_id, order.order_date)
            if order.source == "shop"
            else order.order_date
        )
        order_kg = 0
        if order.items:
            for item in order.items:
                product = products_by_name.get(item.product_name.casefold())
                weight = weight_in_kg(product.weight if product else None)
                if not weight:
                    weight = weight_in_kg(item.product_name)
                order_kg += weight * item.quantity
        elif order.product_name:
            product = products_by_name.get(order.product_name.casefold())
            weight = weight_in_kg(product.weight if product else None)
            if not weight:
                weight = weight_in_kg(order.product_name)
            order_kg = weight * (order.quantity or 1)

        total_kg += order_kg
        if month and paid_date.startswith(month):
            month_kg += order_kg

    return total_kg, month_kg


def finance_totals(month):
    totals = {}
    for period, date_filter in (
        ("total", None),
        ("month", func.substr(Finance.date, 1, 7) == month),
    ):
        for transaction_type in ("income", "expense"):
            query = Finance.query.with_entities(
                func.coalesce(func.sum(Finance.amount), 0)
            ).filter(Finance.type == transaction_type)
            if date_filter is not None:
                query = query.filter(date_filter)
            totals[f"{period}_{transaction_type}"] = query.scalar()

    totals["total_balance"] = totals["total_income"] - totals["total_expense"]
    totals["month_balance"] = totals["month_income"] - totals["month_expense"]
    return totals
