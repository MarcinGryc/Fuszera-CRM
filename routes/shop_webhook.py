import hashlib
import hmac
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func

from extensions import db
from models import Client, Finance, Order, OrderItem

shop_webhook_bp = Blueprint("shop_webhook", __name__)

MAX_BODY_SIZE = 64 * 1024
ALLOWED_STATUSES = {"preview", "pending", "failed", "paid"}
STATUS_PRIORITY = {"preview": 0, "pending": 1, "failed": 2, "paid": 3}


def _text(value, label, maximum, required=True):
    if value is None and not required:
        return ""
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or (required and not value.strip())
    ):
        raise ValueError(f"Nieprawidłowe pole: {label}.")
    return value.strip()


def _date(value, label):
    value = _text(value, label, 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo("Europe/Warsaw"))
        return parsed.date().isoformat()
    except ValueError as error:
        raise ValueError(f"Nieprawidłowa data: {label}.") from error


def _validate_event(event):
    if not isinstance(event, dict):
        raise ValueError("Nieprawidłowe zdarzenie.")

    event_id = _text(event.get("eventId"), "eventId", 160)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", event_id):
        raise ValueError("Nieprawidłowy identyfikator zdarzenia.")

    event_type = event.get("eventType")
    if event_type not in {"order.created", "order.updated"}:
        raise ValueError("Nieobsługiwany typ zdarzenia.")

    order = event.get("order")
    if not isinstance(order, dict):
        raise ValueError("Nieprawidłowe zamówienie.")

    external_id = _text(order.get("id"), "order.id", 32)
    if not re.fullmatch(r"[a-f0-9]{32}", external_id):
        raise ValueError("Nieprawidłowy identyfikator zamówienia.")

    status = order.get("status")
    if status not in ALLOWED_STATUSES:
        raise ValueError("Nieprawidłowy status płatności.")

    total_cents = order.get("totalCents")
    if type(total_cents) is not int or total_cents < 0:
        raise ValueError("Nieprawidłowa wartość zamówienia.")

    if order.get("currency") != "PLN":
        raise ValueError("Nieobsługiwana waluta zamówienia.")

    items = order.get("items")
    if not isinstance(items, list) or not items or len(items) > 99:
        raise ValueError("Zamówienie musi zawierać pozycje.")

    validated_items = []
    item_total = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Nieprawidłowa pozycja zamówienia.")
        name = _text(item.get("name"), "item.name", 255)
        quantity = item.get("qty")
        price_cents = item.get("priceCents")
        line_cents = item.get("lineCents")
        if (
            type(quantity) is not int
            or not 1 <= quantity <= 99
            or type(price_cents) is not int
            or price_cents < 0
            or type(line_cents) is not int
            or line_cents != price_cents * quantity
        ):
            raise ValueError("Nieprawidłowa ilość lub cena produktu.")
        item_total += line_cents
        validated_items.append((name, price_cents, quantity, line_cents))

    shipping = order.get("shipping")
    if not isinstance(shipping, dict):
        raise ValueError("Nieprawidłowe dane dostawy.")
    shipping_label = _text(shipping.get("label"), "shipping.label", 80)
    shipping_cents = shipping.get("priceCents")
    if type(shipping_cents) is not int or shipping_cents < 0:
        raise ValueError("Nieprawidłowy koszt dostawy.")
    if item_total + shipping_cents != total_cents:
        raise ValueError("Suma pozycji nie zgadza się z wartością zamówienia.")

    customer = order.get("customer")
    if not isinstance(customer, dict):
        raise ValueError("Nieprawidłowe dane klienta.")
    first_name = _text(customer.get("firstName"), "customer.firstName", 60)
    last_name = _text(customer.get("lastName"), "customer.lastName", 80)
    email = _text(customer.get("email"), "customer.email", 254)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Nieprawidłowy adres e-mail.")
    phone = _text(customer.get("phone"), "customer.phone", 25, required=False)
    address = _text(customer.get("address"), "customer.address", 120, required=False)
    postal_code = _text(customer.get("postalCode"), "customer.postalCode", 6, required=False)
    city = _text(customer.get("city"), "customer.city", 80, required=False)

    created_date = _date(order.get("createdAt"), "order.createdAt")
    paid_at = order.get("paidAt")
    paid_date = _date(paid_at, "order.paidAt") if paid_at else created_date
    notes = _text(order.get("notes"), "order.notes", 1000, required=False)
    shipping_point = _text(shipping.get("point"), "shipping.point", 20, required=False)
    order_number = _text(order.get("number"), "order.number", 32)

    return {
        "event_id": event_id,
        "event_type": event_type,
        "external_id": external_id,
        "status": status,
        "total": total_cents / 100,
        "created_date": created_date,
        "paid_date": paid_date,
        "order_number": order_number,
        "items": validated_items,
        "customer": {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": address,
            "postal_code": postal_code,
            "city": city,
        },
        "shipping_label": shipping_label,
        "shipping_point": shipping_point,
        "shipping_cents": shipping_cents,
        "notes": notes,
    }


@shop_webhook_bp.route("/integrations/shop/orders", methods=["POST"])
def receive_shop_order():
    secret = current_app.config.get("SHOP_WEBHOOK_SECRET", "")
    if len(secret) < 32:
        return jsonify(error="Integracja sklepu nie jest skonfigurowana."), 503

    if request.mimetype != "application/json":
        return jsonify(error="Wymagany jest format JSON."), 415
    if request.content_length is None or request.content_length > MAX_BODY_SIZE:
        return jsonify(error="Nieprawidłowy rozmiar żądania."), 413

    timestamp = request.headers.get("X-Fuszera-Timestamp", "")
    signature = request.headers.get("X-Fuszera-Signature", "")
    if not re.fullmatch(r"\d{10}", timestamp):
        return jsonify(error="Nieprawidłowy podpis."), 401
    if abs(int(time.time()) - int(timestamp)) > 300:
        return jsonify(error="Podpis żądania wygasł."), 401
    if not re.fullmatch(r"v1=[a-f0-9]{64}", signature):
        return jsonify(error="Nieprawidłowy podpis."), 401

    raw_body = request.get_data(cache=False)
    signed_content = timestamp.encode("ascii") + b"." + raw_body
    expected_signature = "v1=" + hmac.new(
        secret.encode("utf-8"), signed_content, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        return jsonify(error="Nieprawidłowy podpis."), 401

    try:
        event = json.loads(raw_body.decode("utf-8"))
        data = _validate_event(event)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return jsonify(error=str(error)), 400

    crm_order = (
        Order.query.filter_by(source="shop", external_id=data["external_id"])
        .with_for_update()
        .first()
    )
    if crm_order is None and data["status"] != "paid":
        return jsonify(status="received", eventId=data["event_id"]), 200

    email = data["customer"]["email"].casefold()
    client = Client.query.filter(func.lower(Client.email) == email).order_by(Client.id).first()
    if client is None:
        client = Client(
            type="individual",
            name=f"{data['customer']['first_name']} {data['customer']['last_name']}",
            email=data["customer"]["email"],
            phone=data["customer"]["phone"],
            address=", ".join(
                part
                for part in (
                    data["customer"]["address"],
                    data["customer"]["postal_code"],
                    data["customer"]["city"],
                )
                if part
            ),
        )
        db.session.add(client)
        db.session.flush()
    else:
        if not client.phone and data["customer"]["phone"]:
            client.phone = data["customer"]["phone"]
        if not client.address:
            client.address = ", ".join(
                part
                for part in (
                    data["customer"]["address"],
                    data["customer"]["postal_code"],
                    data["customer"]["city"],
                )
                if part
            )

    if crm_order is None:
        first_item = data["items"][0]
        crm_order = Order(
            client_id=client.id,
            product_name=first_item[0],
            quantity=first_item[2],
            total=data["total"],
            order_date=data["paid_date"],
            notes="\n".join(
                part
                for part in (
                    f"Sklep: {data['order_number']}",
                    f"Kontakt: {data['customer']['first_name']} {data['customer']['last_name']}",
                    f"E-mail: {data['customer']['email']}",
                    f"Telefon: {data['customer']['phone']}" if data["customer"]["phone"] else "",
                    "Adres: "
                    + ", ".join(
                        part
                        for part in (
                            data["customer"]["address"],
                            data["customer"]["postal_code"],
                            data["customer"]["city"],
                        )
                        if part
                    ),
                    f"Dostawa: {data['shipping_label']}"
                    + (f" ({data['shipping_point']})" if data["shipping_point"] else "")
                    + f" — {data['shipping_cents'] / 100:.2f} zł",
                    f"Uwagi klienta: {data['notes']}" if data["notes"] else "",
                )
                if part
            ),
            source="shop",
            external_id=data["external_id"],
            payment_status=data["status"],
        )
        db.session.add(crm_order)
        db.session.flush()

        for name, price_cents, quantity, line_cents in data["items"]:
            db.session.add(
                OrderItem(
                    order_id=crm_order.id,
                    product_name=name,
                    unit_price=price_cents / 100,
                    quantity=quantity,
                    line_total=line_cents / 100,
                )
            )
    elif STATUS_PRIORITY[data["status"]] > STATUS_PRIORITY[crm_order.payment_status]:
        crm_order.payment_status = data["status"]
        if crm_order.payment_status == "paid":
            crm_order.order_date = data["paid_date"]

    if crm_order.payment_status == "paid":
        finance_ref = f"shop:{data['external_id']}"
        if Finance.query.filter_by(source_ref=finance_ref).first() is None:
            db.session.add(
                Finance(
                    type="income",
                    title=f"Zamówienie sklepowe {data['order_number']}",
                    amount=crm_order.total,
                    date=data["paid_date"],
                    source_ref=finance_ref,
                )
            )

    db.session.commit()
    return jsonify(status="received", eventId=data["event_id"]), 200
