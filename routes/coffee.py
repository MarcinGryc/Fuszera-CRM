import math

from flask import Blueprint, render_template, request

from routes.auth import login_required

coffee_bp = Blueprint("coffee", __name__)


def calculate_price(green_price_net_per_kg, pack_weight_kg, labor_cost_per_kg_roasted, margin, discount=0):
    values = (green_price_net_per_kg, pack_weight_kg, labor_cost_per_kg_roasted, margin, discount)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Wartości wyceny muszą być liczbami.")
    if green_price_net_per_kg < 0 or pack_weight_kg < 0 or labor_cost_per_kg_roasted < 0:
        raise ValueError("Koszty i gramatura nie mogą być ujemne.")
    if not 0 <= margin < 1 or not 0 <= discount <= 1:
        raise ValueError("Marża lub rabat są poza dozwolonym zakresem.")

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

    price_before_discount = total_cost_per_bag / (1 - margin)
    price_net = price_before_discount * (1 - discount)
    price_gross = price_net * (1 + vat_rate)
    actual_margin = (price_net - total_cost_per_bag) / price_net if price_net else 0

    return {
        "cost_net": round(total_cost_per_bag, 2),
        "net": round(price_net, 2),
        "gross": round(price_gross, 2),
        "margin_pct": round(actual_margin * 100, 2),
    }


def parse_non_negative(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Podaj prawidłową wartość: {label}.") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Wartość {label} nie może być ujemna ani nieprawidłowa.")
    return number


@coffee_bp.route("/coffee-pricing", methods=["GET", "POST"])
@login_required
def coffee_pricing():
    result = None
    error = None

    if request.method == "POST":
        coffee_type = request.form.get("coffee_type")
        try:
            if coffee_type not in {"single", "blend"}:
                raise ValueError("Wybierz prawidłowy typ kawy.")
            labor = parse_non_negative(request.form.get("labor") or "0", "kosztu pracy")

            if coffee_type == "single":
                green_price = parse_non_negative(
                    request.form.get("single_price"), "ceny zielonego ziarna"
                )
            else:
                blend_prices = request.form.getlist("blend_price")
                blend_percentages = request.form.getlist("blend_percentage")
                if len(blend_prices) != len(blend_percentages) or len(blend_prices) > 3:
                    raise ValueError("Nieprawidłowa liczba składników blendu.")
                blend = []

                for price, percentage in zip(blend_prices, blend_percentages):
                    if not price.strip() and not percentage.strip():
                        continue
                    if not price.strip() or not percentage.strip():
                        raise ValueError("Uzupełnij cenę i procent każdego ziarna blendu.")

                    price_value = parse_non_negative(price, "ceny ziarna w blendzie")
                    percentage_value = parse_non_negative(
                        percentage, "udziału procentowego w blendzie"
                    )
                    if not 0 < percentage_value <= 100:
                        raise ValueError("Udział każdego ziarna musi być większy od 0% i nie większy niż 100%.")
                    blend.append((price_value, percentage_value))

                if len(blend) < 2:
                    raise ValueError("Blend musi zawierać co najmniej dwa ziarna.")
                if not math.isclose(sum(row[1] for row in blend), 100, abs_tol=1e-6):
                    raise ValueError("Udziały ziaren w blendzie muszą sumować się do 100%.")

                green_price = sum(price * percentage / 100 for price, percentage in blend)

            result = {
                "green_price": round(green_price, 2),
                "b2c_250": calculate_price(green_price, 0.25, labor, 0.60),
                "b2c_1000": calculate_price(green_price, 1.0, labor, 0.60),
                "b2b_250": calculate_price(green_price, 0.25, labor, 0.60, 0.20),
                "b2b_1000": calculate_price(green_price, 1.0, labor, 0.60, 0.20),
            }
        except ValueError as validation_error:
            error = str(validation_error)

    return render_template("coffee_pricing.html", result=result, error=error)