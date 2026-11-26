"""Magazyn podzielony na kategorie: kolumny w bazie i startowa lista pozycji."""
from sqlalchemy import inspect

from extensions import db
from models import InventoryItem

# (klucz, nazwa sekcji, domyślna jednostka)
CATEGORIES = [
    ("green", "Kawa zielona", "kg"),
    ("roasted", "Kawa palona", "kg"),
    ("packaging", "Opakowania", "szt"),
    ("parcels", "Paczki", "szt"),
]
CATEGORY_KEYS = {key for key, _, _ in CATEGORIES}
DEFAULT_UNITS = {key: unit for key, _, unit in CATEGORIES}

STARTING_ITEMS = {
    "green": ["Brazylia", "Etiopia", "Kenia", "Robusta"],
    "roasted": ["Brazylia", "Kenia", "Etiopia", "Wiśnia", "Wiśnia Przelew", "Wiśnia Espresso", "Robusta"],
    "packaging": ["Kato 250g", "Kato 1kg", "Flat Bottom 250g", "Flat Bottom 1kg", "Doypack 250g", "Doypack 1kg", "Doypack 3kg"],
    "parcels": ["Wiśnia Espresso", "Wiśnia Przelew", "KATO Kawa 250g", "KATO Kawa 1kg", "Sztygarka", "Kenia"],
}


def ensure_inventory_layout():
    """Dodaje kolumny kategorii i kolejności; startową listę wpisuje raz, przy pierwszym uruchomieniu."""
    columns = {column["name"] for column in inspect(db.engine).get_columns("inventory")}
    added = False
    with db.engine.begin() as conn:
        if "category" not in columns:
            conn.exec_driver_sql("ALTER TABLE inventory ADD COLUMN category VARCHAR(30)")
            added = True
        if "sort_order" not in columns:
            conn.exec_driver_sql("ALTER TABLE inventory ADD COLUMN sort_order INTEGER DEFAULT 0")
            added = True

    if not added and InventoryItem.query.count():
        return
    for category, names in STARTING_ITEMS.items():
        for position, name in enumerate(names):
            db.session.add(InventoryItem(
                name=name, quantity=0, unit=DEFAULT_UNITS[category], category=category, sort_order=position,
            ))
    db.session.commit()
