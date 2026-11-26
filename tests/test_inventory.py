import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "isolated-test-key"

from app import create_app, ensure_additive_schema
from extensions import db
from inventory_setup import STARTING_ITEMS, ensure_inventory_layout
from models import InventoryItem


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            ensure_additive_schema()
            ensure_inventory_layout()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["logged_in"] = True

    def names(self, category):
        with self.app.app_context():
            return [i.name for i in InventoryItem.query.filter_by(category=category).order_by(InventoryItem.sort_order).all()]

    def test_starting_list_is_added_once_with_zero_stock(self):
        self.assertEqual(self.names("green"), ["Brazylia", "Etiopia", "Kenia", "Robusta"])
        self.assertEqual(self.names("parcels"), STARTING_ITEMS["parcels"])
        with self.app.app_context():
            self.assertTrue(all(item.quantity == 0 for item in InventoryItem.query.all()))
            total = InventoryItem.query.count()
            ensure_inventory_layout()
            self.assertEqual(InventoryItem.query.count(), total)

    def test_existing_database_gets_columns_and_keeps_old_items(self):
        with self.app.app_context():
            db.drop_all()
            with db.engine.begin() as conn:
                conn.exec_driver_sql("CREATE TABLE inventory (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, quantity FLOAT, unit VARCHAR(50), notes TEXT)")
                conn.exec_driver_sql("INSERT INTO inventory (name, quantity, unit) VALUES ('Stara pozycja', 5, 'kg')")
            db.create_all()  # other tables; the old inventory table stays as it was
            ensure_inventory_layout()
            old = InventoryItem.query.filter_by(name="Stara pozycja").one()
            self.assertIsNone(old.category)
            self.assertEqual(InventoryItem.query.filter_by(category="roasted").count(), len(STARTING_ITEMS["roasted"]))
        page = self.client.get("/inventory").get_data(as_text=True)
        self.assertIn("Bez kategorii", page)
        self.assertIn("Stara pozycja", page)

    def test_page_shows_sections_and_no_products_menu(self):
        page = self.client.get("/inventory").get_data(as_text=True)
        for label in ("Kawa zielona", "Kawa palona", "Opakowania", "Paczki", "Doypack 3kg", "Cennik produktów"):
            self.assertIn(label, page)
        self.assertNotIn('href="/products"', page)

    def test_add_with_category_goes_to_the_end_with_default_unit(self):
        response = self.client.post("/inventory", data={"name": "Kolumbia", "category": "green", "quantity": "12,5"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.names("green")[-1], "Kolumbia")
        with self.app.app_context():
            item = InventoryItem.query.filter_by(name="Kolumbia").one()
            self.assertEqual((item.quantity, item.unit), (12.5, "kg"))
        self.assertEqual(self.client.post("/inventory", data={"name": "X", "category": "nope"}).status_code, 400)

    def test_inline_update_and_reorder_within_category(self):
        with self.app.app_context():
            ids = [i.id for i in InventoryItem.query.filter_by(category="green").order_by(InventoryItem.sort_order).all()]
        saved = self.client.post(f"/inventory/update/{ids[0]}", data={"quantity": "3.5"}, headers={"X-Requested-With": "fetch"})
        self.assertEqual(saved.status_code, 204)
        reordered = list(reversed(ids))
        self.assertEqual(self.client.post("/inventory/reorder", json={"category": "green", "ids": reordered}).status_code, 200)
        self.assertEqual(self.names("green"), ["Robusta", "Kenia", "Etiopia", "Brazylia"])
        # Ids from another category or a stale list are refused.
        self.assertEqual(self.client.post("/inventory/reorder", json={"category": "green", "ids": ids[:2]}).status_code, 409)
        self.assertEqual(self.client.post("/inventory/reorder", json={"category": "bad", "ids": ids}).status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.session.get(InventoryItem, ids[0]).quantity, 3.5)


if __name__ == "__main__":
    unittest.main()
