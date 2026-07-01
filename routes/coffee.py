from flask import Blueprint, render_template, request

from routes.auth import login_required

coffee_bp = Blueprint("coffee", __name__)


def calculate_price(green_price_net_per_kg, pack_weight_kg, labor_cost_per_kg_roasted, margin, discount=0):
    roast_loss = 0.18
    packaging_cost_per_bag = 5
    vat_rate = 0.23
    gas_cost_per_kg = 1
    fixed_cost_per_kg = 3.03

    total_cost_per_kg = (
        green_price_net_per_kg / (1 - roast_loss)
        + gas_cost_per_kg
        + fixed_cost_per_kg
        + labor_cost_per_kg_roasted
    )

    coffee_cost_per_bag = total_cost_per_kg * pack_weight_kg
    total_cost_per_bag = coffee_cost_per_bag + packaging_cost_per_bag

    price_net = total_cost_per_bag / (1 - margin)
    price_net = price_net * (1 - discount)
    price_gross = price_net * (1 + vat_rate)

    return {
        "cost_net": round(total_cost_per_bag, 2),
        "net": round(price_net, 2),
        "gross": round(price_gross, 2),
    }


@coffee_bp.route("/coffee-pricing", methods=["GET", "POST"])
@login_required
def coffee_pricing():
    result = None

    if request.method == "POST":
        coffee_type = request.form.get("coffee_type")
        labor = float(request.form.get("labor") or 0)

        if coffee_type == "single":
            green_price = float(request.form.get("single_price") or 0)
        else:
            blend_prices = request.form.getlist("blend_price")
            blend_percentages = request.form.getlist("blend_percentage")

            green_price = 0
            for price, percentage in zip(blend_prices, blend_percentages):
                if price and percentage:
                    green_price += float(price) * (float(percentage) / 100)

        result = {
            "green_price": round(green_price, 2),
            "b2c_250": calculate_price(green_price, 0.25, labor, 0.60, 0),
            "b2c_1000": calculate_price(green_price, 1.0, labor, 0.60, 0),
            "b2b_250": calculate_price(green_price, 0.25, labor, 0.45, 0.20),
            "b2b_1000": calculate_price(green_price, 1.0, labor, 0.45, 0.20),
        }

    return render_template("coffee_pricing.html", result=result)