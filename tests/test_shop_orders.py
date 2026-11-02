import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "isolated-test-key"
os.environ["SHOP_WEBHOOK_SECRET"] = "test-webhook-secret-" * 2

import app as app_module
from app import create_app, ensure_additive_schema
from extensions import db
from models import Client, Finance, Order, OrderItem, Product
from routes.coffee import calculate_price
from routes.order_metrics import current_month
from routes.offers import send_offer_email, test_email_connection as check_email_connection


SECRET = os.environ["SHOP_WEBHOOK_SECRET"]


def signed_headers(body, secret=SECRET):
    timestamp = str(int(time.time()))
    digest = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Fuszera-Timestamp": timestamp,
        "X-Fuszera-Signature": f"v1={digest}",
    }


def shop_event(event_id, status, paid_at=None):
    return {
        "eventId": event_id,
        "eventType": "order.created" if status == "pending" else "order.updated",
        "order": {
            "id": "a" * 32,
            "number": "F-000123",
            "status": status,
            "totalCents": 9583,
            "currency": "PLN",
            "createdAt": "2026-11-02T10:00:00.000Z",
            "paidAt": paid_at,
            "items": [
                {
                    "id": "coffee-250",
                    "name": "Kawa 250 g",
                    "qty": 2,
                    "priceCents": 4000,
                    "lineCents": 8000,
                }
            ],
            "shipping": {
                "id": "inpost-locker",
                "label": "Paczkomat",
                "priceCents": 1583,
                "point": "ABC123",
            },
            "customer": {
                "firstName": "Jan",
                "lastName": "Kowalski",
                "email": "jan@example.test",
                "phone": "+48123456789",
                "address": "Testowa 1",
                "postalCode": "00-001",
                "city": "Warszawa",
            },
            "notes": "",
        },
    }


class ShopOrderSyncTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SHOP_WEBHOOK_SECRET=SECRET)
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            ensure_additive_schema()
        self.client = self.app.test_client()

    def post_event(self, event, headers=None):
        body = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return self.client.post(
            "/integrations/shop/orders",
            data=body,
            headers=headers or signed_headers(body),
        )

    def test_paid_shop_order_is_recorded_once_in_finances(self):
        created = self.post_event(shop_event("created-event", "pending"))
        self.assertEqual(created.status_code, 200)

        with self.app.app_context():
            self.assertEqual(Order.query.filter_by(source="shop").count(), 0)
            self.assertEqual(Client.query.count(), 0)
            self.assertEqual(Finance.query.count(), 0)

        paid_event = shop_event("paid-event", "paid", "2026-11-02T11:00:00.000Z")
        self.assertEqual(self.post_event(paid_event).status_code, 200)
        self.assertEqual(self.post_event(paid_event).status_code, 200)
        self.assertEqual(self.post_event(shop_event("created-event", "pending")).status_code, 200)

        with self.app.app_context():
            self.assertEqual(Order.query.filter_by(source="shop").count(), 1)
            order = Order.query.one()
            self.assertEqual(order.payment_status, "paid")
            self.assertEqual(order.order_date, "2026-11-02")
            self.assertEqual(OrderItem.query.filter_by(order_id=order.id).count(), 1)
            self.assertEqual(Finance.query.count(), 1)
            finance = Finance.query.one()
            self.assertEqual(finance.amount, 95.83)
            self.assertEqual(finance.date, "2026-11-02")

    def test_invalid_signature_does_not_create_order(self):
        event = shop_event("created-event", "pending")
        body = json.dumps(event, separators=(",", ":")).encode("utf-8")
        response = self.post_event(
            event,
            {
                **signed_headers(body),
                "X-Fuszera-Signature": "v1=" + "0" * 64,
            },
        )
        self.assertEqual(response.status_code, 401)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)

    def test_manual_order_creates_income_entry(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.post(
            "/orders",
            data={
                "product_name": ["Kawa 250 g"],
                "unit_price": ["10.00"],
                "quantity": ["2"],
                "total": "20.00",
                "order_date": "2026-11-02",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(Order.query.filter_by(source="manual").count(), 1)
            self.assertEqual(Finance.query.count(), 1)
            self.assertEqual(Finance.query.one().amount, 20.0)

    def test_manual_order_rejects_non_finite_price_without_finance_entry(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.post(
            "/orders",
            data={
                "product_name": ["Kawa 250 g"],
                "unit_price": ["nan"],
                "quantity": ["2"],
                "total": "20.00",
                "order_date": "2026-11-02",
            },
        )
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(Finance.query.count(), 0)

    def test_orders_page_shows_monthly_and_total_coffee_weight_for_paid_orders(self):
        month = current_month()
        with self.app.app_context():
            product = Product(name="Kawa klasyczna", weight="250 g", price=20)
            db.session.add(product)
            manual_order = Order(
                product_name="Kawa klasyczna",
                quantity=4,
                total=80,
                order_date=f"{month}-02",
                source="manual",
                payment_status="manual",
            )
            paid_order = Order(
                product_name="Kawa 250 g",
                quantity=2,
                total=40,
                order_date=f"{month}-03",
                source="shop",
                external_id="b" * 32,
                payment_status="paid",
            )
            pending_order = Order(
                product_name="Kawa 250 g",
                quantity=100,
                total=2000,
                order_date=f"{month}-04",
                source="shop",
                external_id="c" * 32,
                payment_status="pending",
                notes="UNPAID-ORDER",
            )
            db.session.add_all((manual_order, paid_order, pending_order))
            db.session.add(
                OrderItem(
                    order=paid_order,
                    product_name="Kawa 250 g",
                    unit_price=20,
                    quantity=2,
                    line_total=40,
                )
            )
            db.session.add(
                OrderItem(
                    order=pending_order,
                    product_name="Kawa 250 g",
                    unit_price=20,
                    quantity=100,
                    line_total=2000,
                )
            )
            db.session.add_all(
                (
                    Finance(type="income", title="Historyczny", amount=99, date="2020-01-01"),
                    Finance(type="income", title="Bieżący", amount=40, date=f"{month}-03"),
                    Finance(type="expense", title="Stary wydatek", amount=25, date="2020-01-01"),
                    Finance(type="expense", title="Wydatek bieżący", amount=10, date=f"{month}-03"),
                )
            )
            db.session.commit()

        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.get("/orders")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("1.500 kg", page)
        self.assertNotIn("UNPAID-ORDER", page)

        finance_response = self.client.get("/finances")
        finance_page = finance_response.get_data(as_text=True)
        self.assertEqual(finance_response.status_code, 200)
        self.assertIn("139.00 zł", finance_page)
        self.assertIn("40.00 zł", finance_page)
        self.assertIn("35.00 zł", finance_page)
        self.assertIn("10.00 zł", finance_page)
        self.assertIn("104.00 zł", finance_page)
        self.assertIn("30.00 zł", finance_page)

        dashboard_response = self.client.get("/")
        dashboard_page = dashboard_response.get_data(as_text=True)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("1.500 kg", dashboard_page)
        self.assertIn("139.00 zł", dashboard_page)
        self.assertIn("40.00 zł", dashboard_page)
        self.assertIn("35.00 zł", dashboard_page)
        self.assertIn("10.00 zł", dashboard_page)
        self.assertIn("104.00 zł", dashboard_page)
        self.assertIn("30.00 zł", dashboard_page)

    def test_b2b_price_is_discounted_from_b2c_price(self):
        retail = calculate_price(40, 0.25, 0, 0.60)
        b2b = calculate_price(40, 0.25, 0, 0.60, 0.20)
        self.assertAlmostEqual(b2b["net"], retail["net"] * 0.8, places=2)
        self.assertLess(b2b["margin_pct"], retail["margin_pct"])

    def test_blend_requires_percentages_to_sum_to_100(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.post(
            "/coffee-pricing",
            data={
                "coffee_type": "blend",
                "labor": "0",
                "blend_price": ["40", "30", ""],
                "blend_percentage": ["50", "40", ""],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("muszą sumować się do 100%", response.get_data(as_text=True))

    def test_resend_offer_uses_bcc_without_exposing_recipients(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        recipients = [f"client{index}@example.test" for index in range(52)]

        with patch.dict(
            os.environ,
            {
                "EMAIL_PROVIDER": "resend",
                "RESEND_API_KEY": "test-key",
                "SMTP_FROM": "offers@example.test",
            },
        ), patch("routes.offers.urlopen", return_value=response) as urlopen_mock:
            send_offer_email("Oferta", "Treść", recipients, "bcc")
            check_email_connection()

        self.assertEqual(urlopen_mock.call_count, 3)
        first_request = urlopen_mock.call_args_list[0].args[0]
        payload = json.loads(first_request.data.decode("utf-8"))
        self.assertEqual(payload["to"], ["offers@example.test"])
        self.assertEqual(len(payload["bcc"]), 49)
        self.assertNotIn("client0@example.test", payload["to"])

    def test_schema_extension_preserves_legacy_orders_and_finances(self):
        with self.app.app_context():
            db.drop_all()
            with db.engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE TABLE orders (id INTEGER PRIMARY KEY, client_id INTEGER, "
                    "product_name VARCHAR(255) NOT NULL, quantity INTEGER NOT NULL, "
                    "total FLOAT NOT NULL, order_date VARCHAR(20) NOT NULL, notes TEXT)"
                )
                conn.exec_driver_sql(
                    "CREATE TABLE finances (id INTEGER PRIMARY KEY, type VARCHAR(30) NOT NULL, "
                    "title VARCHAR(255) NOT NULL, amount FLOAT NOT NULL, date VARCHAR(20) NOT NULL)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO orders VALUES (7, NULL, 'Kawa 250 g', 2, 20, '2026-11-02', NULL)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO finances VALUES (4, 'income', 'Historia', 20, '2026-11-02')"
                )
            ensure_additive_schema()
            with db.engine.connect() as conn:
                order = conn.exec_driver_sql(
                    "SELECT product_name, quantity, source, payment_status FROM orders WHERE id=7"
                ).one()
                finance = conn.exec_driver_sql(
                    "SELECT title, amount, source_ref FROM finances WHERE id=4"
                ).one()
            self.assertEqual(tuple(order), ("Kawa 250 g", 2, "manual", "manual"))
            self.assertEqual(tuple(finance), ("Historia", 20, None))

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    @classmethod
    def tearDownClass(cls):
        with app_module.app.app_context():
            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
