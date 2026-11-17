import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from flask import Blueprint, jsonify, render_template, request
from routes.auth import login_required

coffee_bp = Blueprint("coffee", __name__)
DEFAULTS = {
    "blend_price": [40, 40, 40], "blend_percentage": [100, 0, 0],
    "packaging": 5, "production": 5, "fixed_monthly": 1500, "monthly_kg": 200,
    "roast_loss": 18, "extra_per_bag": 0, "sales_fee": 0,
    "margin": 48.72, "discount": 20,
}
VAT_RATE = Decimal("0.23")
CENT = Decimal("0.01")


def decimal(value):
    return Decimal(str(value))


def money(value, rounding=ROUND_HALF_UP):
    return float(value.quantize(CENT, rounding=rounding))


def parse_non_negative(value, label):
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Podaj prawidłową wartość: {label}.") from error
    if not math.isfinite(number) or number < 0 or number > 1e9:
        raise ValueError(f"Wartość {label} musi być nieujemną, skończoną liczbą do 1 mld.")
    return number


def calculate_price(green_price_net_per_kg, pack_weight_kg, production_cost_per_kg_roasted,
                    markup, discount=0, *, packaging=5, fixed_monthly=1500,
                    monthly_kg=200, roast_loss=0.18, extra_per_bag=0, sales_fee=0,
                    round_retail_gross=False):
    """Allocate overhead to kilograms of roasted coffee sold, without double-counting
    labor/gas/electricity already in production. Sales fees use NET revenue as base.
    Round prices up to cents so a break-even price never falls below full cost.
    """
    values = (green_price_net_per_kg, pack_weight_kg, production_cost_per_kg_roasted,
              markup, discount, packaging, fixed_monthly, monthly_kg, roast_loss,
              extra_per_bag, sales_fee)
    if not all(math.isfinite(v) and 0 <= v <= 1e9 for v in values):
        raise ValueError("Wartości wyceny muszą być nieujemnymi, skończonymi liczbami do 1 mld.")
    if pack_weight_kg <= 0 or monthly_kg < 0.01:
        raise ValueError("Gramatura musi być większa od zera, a miesięczna sprzedaż wynosić co najmniej 0,01 kg.")
    if not 0 <= discount <= 1:
        raise ValueError("Rabat musi mieścić się w zakresie 0–100%.")
    if not 0 <= roast_loss <= 0.9999 or not 0 <= sales_fee <= 0.9999:
        raise ValueError("Ubytek i prowizja muszą mieścić się w zakresie 0–99,99%.")
    green, weight, production, markup, discount, packaging, fixed, volume, loss, extra, fee = map(decimal, values)
    bean_cost = green / (1 - loss) * weight
    production_cost = production * weight
    fixed_cost = fixed / volume * weight
    variable_cost = bean_cost + production_cost + packaging + extra
    cost = variable_cost + fixed_cost
    if cost == 0:
        raise ValueError("Koszt paczki musi być większy od zera. Uzupełnij rzeczywiste koszty.")
    retail = decimal(money(cost * (1 + markup) / (1 - fee), ROUND_CEILING))
    retail_gross = None
    if round_retail_gross:
        # One shared margin; whole-zloty retail prices retain the 49/159 baseline.
        # Round the unrounded target UP, then derive the net invoice price.
        retail_gross = (cost * (1 + markup) / (1 - fee) * (1 + VAT_RATE)).quantize(
            Decimal(1), rounding=ROUND_CEILING)
        retail = decimal(money(retail_gross / (1 + VAT_RATE)))
        # Invoice cent rounding must not put a zero-margin sale below full cost.
        if retail * (1 - fee) < cost:
            retail_gross += 1
            retail = decimal(money(retail_gross / (1 + VAT_RATE)))
    if retail_gross is None:
        price = decimal(money(retail * (1 - discount), ROUND_CEILING))
        gross = money(price * (1 + VAT_RATE))
    else:
        # Apply the café discount to the advertised B2C price, avoiding a penny
        # surcharge from applying and rounding the discount twice through VAT.
        gross = money(retail_gross * (1 - discount))
        price = decimal(money(decimal(gross) / (1 + VAT_RATE)))
    commission = price * fee
    profit = price - commission - cost
    contribution = price - commission - variable_cost
    break_even_kg = fixed / contribution * weight if contribution > 0 else None
    # Floor the quoted discount limit to avoid advertising a loss-making discount.
    max_discount = max(Decimal(0), (1 - cost / (retail * (1 - fee))) * 100)
    if retail_gross is not None:
        minimum_net = decimal(money(cost / (1 - fee), ROUND_CEILING))
        minimum_gross = decimal(money(minimum_net * (1 + VAT_RATE), ROUND_CEILING))
        max_discount = max(Decimal(0), (1 - minimum_gross / retail_gross) * 100)
    return {
        "cost_net": money(cost), "beans": money(bean_cost),
        "production": money(production_cost), "fixed": money(fixed_cost),
        "packaging": money(packaging), "extra": money(extra),
        "net": float(price), "gross": gross,
        "fee": money(commission), "profit": money(profit),
        "margin_pct": money(profit / price * 100) if price else None,
        "max_discount_pct": money(max_discount, ROUND_FLOOR),
        "break_even_kg": money(break_even_kg, ROUND_CEILING) if break_even_kg is not None else None,
        "monthly_profit": money(profit * volume / weight), "below_cost": profit < 0,
    }


def calculate_quote(form):
    prices, percentages = form.getlist("blend_price"), form.getlist("blend_percentage")
    if len(prices) != 3 or len(percentages) != 3:
        raise ValueError("Podaj cenę i udział dla trzech kaw; nieużywane kawy ustaw na 0%.")
    prices = [parse_non_negative(v, "ceny ziarna") for v in prices]
    percentages = [parse_non_negative(v, "udziału w blendzie") for v in percentages]
    if any(v > 100 for v in percentages) or not math.isclose(sum(percentages), 100, abs_tol=1e-6):
        raise ValueError("Udziały ziaren w blendzie muszą sumować się do 100%.")
    if any(price <= 0 and share > 0 for price, share in zip(prices, percentages)):
        raise ValueError("Cena każdej używanej kawy musi być większa od zera.")
    labels = {"packaging": "opakowania", "production": "produkcji", "fixed_monthly": "kosztów stałych",
              "monthly_kg": "miesięcznej sprzedaży", "roast_loss": "ubytku", "extra_per_bag": "pozostałych kosztów",
              "sales_fee": "prowizji", "margin": "marży", "discount": "rabatu"}
    inputs = {key: parse_non_negative(form.get(key), label) for key, label in labels.items()}
    if not 0 <= inputs["margin"] < 100:
        raise ValueError("Marża musi być mniejsza niż 100%.")
    margin = decimal(inputs["margin"]) / 100
    fee = decimal(inputs["sales_fee"]) / 100
    if margin + fee >= 1:
        raise ValueError("Marża i prowizja muszą łącznie wynosić mniej niż 100%.")
    markup = margin / (1 - fee - margin)
    green = sum(decimal(p) * decimal(s) / 100 for p, s in zip(prices, percentages))
    kwargs = {key: inputs[key] for key in ("packaging", "fixed_monthly", "monthly_kg", "extra_per_bag")}
    kwargs.update(roast_loss=inputs["roast_loss"] / 100, sales_fee=inputs["sales_fee"] / 100,
                  round_retail_gross=True)
    result = {"green_price": money(green)}
    for size, weight in (("250", 0.25), ("1000", 1)):
        for channel, discount in (("b2c", 0), ("b2b", inputs["discount"] / 100)):
            result[f"{channel}_{size}"] = calculate_price(
                float(green), weight, inputs["production"], float(markup), discount, **kwargs)
    result["fixed_per_kg"] = money(decimal(inputs["fixed_monthly"]) / decimal(inputs["monthly_kg"]))
    result["max_discount_pct"] = min(result[f"b2c_{size}"]["max_discount_pct"] for size in ("250", "1000"))
    return result


@coffee_bp.route("/coffee-pricing", methods=["GET", "POST"])
@login_required
def coffee_pricing():
    result, error = None, None
    values = dict(DEFAULTS)
    if request.method == "POST":
        values.update({key: request.form.get(key, "") for key in DEFAULTS
                       if key not in {"blend_price", "blend_percentage"}})
        for key in ("blend_price", "blend_percentage"):
            values[key] = (request.form.getlist(key) + [""] * 3)[:3]
        try:
            result = calculate_quote(request.form)
        except ValueError as validation_error:
            error = str(validation_error)
        if request.accept_mimetypes.best == "application/json":
            return jsonify(result=result, error=error), 422 if error else 200
    return render_template("coffee_pricing.html", values=values, result=result, error=error)
