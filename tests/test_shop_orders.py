import hashlib
import hmac
import json
import os
import time
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from openpyxl import Workbook, load_workbook

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "isolated-test-key"
os.environ["SHOP_WEBHOOK_SECRET"] = "test-webhook-secret-" * 2

import app as app_module
from app import create_app, ensure_additive_schema
from extensions import db
from models import Client, DistributionContact, Finance, Order, OrderItem, Product, Supplier
from routes.coffee import calculate_price
from routes.distribution_contacts import distribution_lists
from routes.order_metrics import current_month, sold_coffee_weight
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
        self.app.config.update(TESTING=True, SHOP_WEBHOOK_SECRET=SECRET, OFFERS_ENABLED=False)
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

    def test_paid_shop_order_is_recorded_once_without_finance_entry(self):
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
            self.assertEqual(Finance.query.count(), 0)
            self.assertEqual([contact["email"] for contact in distribution_lists()["individual"]],
                             ["jan@example.test"])

    def test_shop_replay_preserves_existing_finance_entry(self):
        with self.app.app_context():
            db.session.add(Finance(
                type="income", title="Istniejący wpis", amount=50,
                date="2020-01-01", source_ref="shop:" + "a" * 32,
            ))
            db.session.commit()

        paid_event = shop_event("paid-event", "paid", "2026-11-02T11:00:00.000Z")
        self.assertEqual(self.post_event(paid_event).status_code, 200)
        self.assertEqual(self.post_event(paid_event).status_code, 200)

        with self.app.app_context():
            self.assertEqual(Finance.query.count(), 1)
            finance = Finance.query.one()
            self.assertEqual((finance.title, finance.amount, finance.date),
                             ("Istniejący wpis", 50, "2020-01-01"))
            self.assertEqual(sold_coffee_weight(Order.query.all(), [], "2026-11"),
                             (0.5, 0.5))

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

    def test_manual_order_does_not_create_finance_entry(self):
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
            order = Order.query.one()
            self.assertEqual(order.total, 20.0)
            self.assertEqual(OrderItem.query.filter_by(order_id=order.id).count(), 1)
            self.assertEqual(Finance.query.count(), 0)

        with self.client.session_transaction() as session:
            session["logged_in"] = True
        orders_page = self.client.get("/orders").get_data(as_text=True)
        self.assertIn("<th>Tytuł</th>", orders_page)
        self.assertIn("Zamówienie #1:", orders_page)
        self.assertNotIn("<th>Klient</th>", orders_page)

    def test_finance_entries_can_be_added_and_deleted_without_orders(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.post("/finances", data={
            "type": "income", "title": "Wpłata ręczna", "amount": "123.45",
            "date": "2026-11-02",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            finance = Finance.query.one()
            self.assertEqual(finance.amount, 123.45)
            self.assertEqual(Order.query.count(), 0)
            finance_id = finance.id
        response = self.client.post(f"/finances/delete/{finance_id}")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(Finance.query.count(), 0)
            self.assertEqual(Order.query.count(), 0)

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
        self.assertIn("1,5 kg", page)
        self.assertNotIn("UNPAID-ORDER", page)

        finance_response = self.client.get(f"/finances?month={month}")
        finance_page = finance_response.get_data(as_text=True)
        self.assertEqual(finance_response.status_code, 200)
        self.assertIn("139.00 zł", finance_page)
        self.assertIn("40.00 zł", finance_page)
        self.assertIn("35.00 zł", finance_page)
        self.assertIn("10.00 zł", finance_page)
        self.assertIn("104.00 zł", finance_page)
        self.assertIn("30.00 zł", finance_page)

        dashboard_response = self.client.get(f"/?month={month}")
        dashboard_page = dashboard_response.get_data(as_text=True)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("1,5 kg", dashboard_page)
        self.assertIn("139.00 zł", dashboard_page)
        self.assertNotIn("W tym miesiącu", dashboard_page)
        self.assertNotIn('name="month"', dashboard_page)
        self.assertNotIn(f"— {month}", dashboard_page)
        self.assertNotIn("Pokaż miesiąc", dashboard_page)

        previous_finances = self.client.get("/finances?month=2020-01")
        previous_page = previous_finances.get_data(as_text=True)
        self.assertEqual(previous_finances.status_code, 200)
        self.assertIn("99.00 zł", previous_page)
        self.assertIn("25.00 zł", previous_page)
        self.assertIn("74.00 zł", previous_page)
        self.assertIn('value="2020-01"', previous_page)

    def test_month_selection_defaults_to_current_calendar_month(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.get("/finances")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'value="{current_month()}"', response.get_data(as_text=True))
        self.assertEqual(self.client.get("/finances?month=not-a-month").status_code, 400)

    def test_product_can_be_edited_from_expanding_product_row(self):
        with self.app.app_context():
            product = Product(name="Kawa testowa", weight="250 g", price=20)
            db.session.add(product)
            db.session.commit()
            product_id = product.id

        with self.client.session_transaction() as session:
            session["logged_in"] = True
        page = self.client.get("/products?q=Kawa")
        page_text = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("<summary>Edytuj</summary>", page_text)
        delete_position = page_text.index(f'action="/products/delete/{product_id}"')
        edit_position = page_text.index(f'action="/products/edit/{product_id}"')
        self.assertLess(delete_position, edit_position)
        self.assertIn(f'action="/products/edit/{product_id}"', page_text)

        response = self.client.post(
            f"/products/edit/{product_id}",
            data={"name": "Kawa zmieniona", "weight": "1 kg", "price": "45.50", "q": "Kawa"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/products?q=Kawa", response.headers["Location"])
        with self.app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.name, "Kawa zmieniona")
            self.assertEqual(product.weight, "1 kg")
            self.assertEqual(product.price, 45.5)

    def test_clients_and_suppliers_edit_inline_after_delete_button(self):
        with self.app.app_context():
            client = Client(type="b2b", name="Anna Nowak", company="Kawa Test")
            supplier = Supplier(name="Palarnia Test", supplies="Ziarno")
            db.session.add_all((client, supplier))
            db.session.commit()
            client_id, supplier_id = client.id, supplier.id

        with self.client.session_transaction() as session:
            session["logged_in"] = True

        clients_page = self.client.get("/clients?q=Kawa")
        clients_html = clients_page.get_data(as_text=True)
        self.assertEqual(clients_page.status_code, 200)
        delete_position = clients_html.index(f'action="/clients/delete/{client_id}"')
        edit_position = clients_html.index(f'action="/clients/edit/{client_id}"')
        self.assertLess(delete_position, edit_position)
        self.assertIn("<summary>Edytuj</summary>", clients_html)
        self.assertEqual(self.client.get(f"/clients/edit/{client_id}").status_code, 405)
        response = self.client.post(
            f"/clients/edit/{client_id}",
            data={
                "type": "b2b",
                "name": "Anna Nowak",
                "company": "Kawa Nowa",
                "nip": "",
                "email": "",
                "phone": "",
                "address": "",
                "notes": "",
                "q": "Kawa",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/clients?q=Kawa", response.headers["Location"])

        suppliers_page = self.client.get("/suppliers?q=Palarnia")
        suppliers_html = suppliers_page.get_data(as_text=True)
        self.assertEqual(suppliers_page.status_code, 200)
        delete_position = suppliers_html.index(f'action="/suppliers/delete/{supplier_id}"')
        edit_position = suppliers_html.index(f'action="/suppliers/edit/{supplier_id}"')
        self.assertLess(delete_position, edit_position)
        self.assertIn("<summary>Edytuj</summary>", suppliers_html)
        response = self.client.post(
            f"/suppliers/edit/{supplier_id}",
            data={
                "name": "Palarnia Zmieniona",
                "supplies": "Kawa zielona",
                "email": "",
                "phone": "",
                "nip": "",
                "address": "",
                "q": "Palarnia",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/suppliers?q=Palarnia", response.headers["Location"])
        self.assertEqual(self.client.get(f"/suppliers/edit/{supplier_id}").status_code, 405)
        with self.app.app_context():
            self.assertEqual(db.session.get(Supplier, supplier_id).name, "Palarnia Zmieniona")

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

    def test_distribution_combines_clients_and_manual_contacts_without_duplicates(self):
        with self.app.app_context():
            db.session.add_all([
                Client(type="b2b", name="Firma", email=" Firma@Example.test "),
                Client(type="b2b", name="Duplikat", email="firma@example.test"),
                Client(type="individual", name="Osoba", email="firma@example.test"),
                Client(type="individual", name="Pusty", email=""),
                Client(type="individual", name="Błędny", email="brak-adresu"),
                Client(type="individual", name="Wiele adresów", email="a@test.pl\nb@test.pl"),
                DistributionContact(list_type="b2b", email="FIRMA@example.test"),
                DistributionContact(list_type="b2b", email="firma@example.test"),
                DistributionContact(list_type="individual", email="reczny@example.test"),
            ])
            db.session.commit()
            lists = distribution_lists()
            self.assertEqual([item["email"] for item in lists["b2b"]], ["firma@example.test"])
            self.assertEqual([item["email"] for item in lists["individual"]],
                             ["firma@example.test", "reczny@example.test"])

        with self.client.session_transaction() as session:
            session["logged_in"] = True
        page = self.client.get("/distribution")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Z kartoteki klienta", page.get_data(as_text=True))
        response = self.client.get("/distribution/export")
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.data))
        rows = list(workbook.active.iter_rows(min_row=2, values_only=True))
        self.assertEqual([(row[1], row[2]) for row in rows], [
            ("B2B", "firma@example.test"),
            ("Indywidualni", "firma@example.test"),
            ("Indywidualni", "reczny@example.test"),
        ])
        workbook.close()

    def test_distribution_tracks_client_creation_edit_import_and_deletion(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        response = self.client.post("/clients", data={
            "type": "individual", "name": "Klient", "email": "old@example.test",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            client_id = Client.query.one().id
            self.assertEqual(distribution_lists()["individual"][0]["email"], "old@example.test")
        response = self.client.post(f"/clients/edit/{client_id}", data={
            "type": "b2b", "name": "Klient", "email": "new@example.test",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            lists = distribution_lists()
            self.assertEqual(lists["individual"], [])
            self.assertEqual([item["email"] for item in lists["b2b"]], ["new@example.test"])
        response = self.client.post(f"/clients/delete/{client_id}")
        self.assertEqual(response.status_code, 302)

        workbook = Workbook()
        workbook.active.append(["Typ", "Nazwa", "Email"])
        workbook.active.append(["B2B", "Import", "import@example.test"])
        upload = BytesIO()
        workbook.save(upload)
        workbook.close()
        upload.seek(0)
        response = self.client.post("/clients/import", data={"file": (upload, "clients.xlsx")})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            lists = distribution_lists()
            self.assertEqual(lists["individual"], [])
            self.assertEqual([item["email"] for item in lists["b2b"]], ["import@example.test"])

    def test_distribution_manual_add_import_and_delete_deduplicate_addresses(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        for email in (" Test@Example.test ", "test@example.test"):
            response = self.client.post("/distribution", data={"list_type": "b2b", "email": email})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.post("/distribution", data={
            "list_type": "b2b", "email": "invalid",
        }).status_code, 400)
        workbook = Workbook()
        workbook.active.append(["Lista", "Email"])
        workbook.active.append(["B2B", "TEST@example.test"])
        workbook.active.append(["B2B", "other@example.test"])
        workbook.active.append(["B2B", "other@example.test"])
        workbook.active.append(["B2B", "invalid"])
        upload = BytesIO()
        workbook.save(upload)
        workbook.close()
        upload.seek(0)
        self.assertEqual(self.client.post("/distribution/import", data={
            "file": (upload, "contacts.xlsx"),
        }).status_code, 302)
        with self.app.app_context():
            self.assertEqual(DistributionContact.query.count(), 2)
            contact_id = DistributionContact.query.filter_by(email="test@example.test").one().id
            db.session.add(DistributionContact(list_type="b2b", email=" TEST@example.test "))
            db.session.commit()
        self.assertEqual(self.client.post(f"/distribution/delete/{contact_id}").status_code, 302)
        with self.app.app_context():
            self.assertEqual([item["email"] for item in distribution_lists()["b2b"]],
                             ["other@example.test"])

    def test_offers_work_in_progress_blocks_sending_and_connection_tests(self):
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        page = self.client.get("/offers")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Work in progress", page.get_data(as_text=True))
        self.assertNotIn('name="subject"', page.get_data(as_text=True))
        with patch("routes.offers.send_offer_email") as send, patch("routes.offers.test_email_connection") as check:
            for action in ("send_offer", "test_smtp"):
                response = self.client.post("/offers", data={"action": action})
                self.assertEqual(response.status_code, 409)
                self.assertIn("Work in progress", response.get_data(as_text=True))
            send.assert_not_called()
            check.assert_not_called()

    def test_offers_can_be_enabled_later_and_use_the_combined_distribution_list(self):
        self.app.config["OFFERS_ENABLED"] = True
        with self.app.app_context():
            db.session.add_all([
                Client(type="b2b", name="Klient", email="client@example.test"),
                DistributionContact(list_type="b2b", email="CLIENT@example.test"),
                DistributionContact(list_type="b2b", email="manual@example.test"),
            ])
            db.session.commit()
        with self.client.session_transaction() as session:
            session["logged_in"] = True
        page = self.client.get("/offers").get_data(as_text=True)
        self.assertIn("Klienci B2B (2)", page)
        self.assertNotIn("Work in progress", page)
        with patch("routes.offers.send_offer_email") as send:
            response = self.client.post("/offers", data={
                "action": "send_offer", "list_type": "b2b", "subject": "Oferta",
                "body": "Treść", "mode": "bcc",
            })
            self.assertEqual(response.status_code, 200)
            send.assert_called_once_with("Oferta", "Treść",
                                         ["client@example.test", "manual@example.test"], "bcc")

    def test_smtp_offer_remains_ready_for_future_configuration(self):
        with patch.dict(os.environ, {
            "EMAIL_PROVIDER": "smtp", "SMTP_HOST": "smtp.example.test", "SMTP_PORT": "587",
            "SMTP_SECURITY": "starttls", "SMTP_USER": "test-user", "SMTP_PASSWORD": "test-password",
            "SMTP_FROM": "offers@example.test",
        }), patch("routes.offers.smtplib.SMTP") as smtp:
            send_offer_email("Oferta", "Treść", ["client@example.test"], "bcc")
            smtp.assert_called_once_with("smtp.example.test", 587, timeout=60)
            smtp.return_value.starttls.assert_called_once()
            smtp.return_value.login.assert_called_once_with("test-user", "test-password")
            message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            self.assertEqual(message["Bcc"], "client@example.test")

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
