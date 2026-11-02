from flask import Flask
from config import Config
from extensions import db, migrate


def ensure_additive_schema():
    backend = db.engine.url.get_backend_name()

    with db.engine.begin() as conn:
        if backend == "postgresql":
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_name VARCHAR(255)"
            )
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER"
            )
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS source VARCHAR(30) NOT NULL DEFAULT 'manual'"
            )
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS external_id VARCHAR(100)"
            )
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status VARCHAR(30) NOT NULL DEFAULT 'manual'"
            )
            conn.exec_driver_sql(
                "ALTER TABLE finances ADD COLUMN IF NOT EXISTS source_ref VARCHAR(140)"
            )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_source_external_id "
                "ON orders (source, external_id)"
            )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_finances_source_ref "
                "ON finances (source_ref)"
            )
        elif backend == "sqlite":
            order_columns = {
                column[1]
                for column in conn.exec_driver_sql("PRAGMA table_info(orders)").fetchall()
            }
            finance_columns = {
                column[1]
                for column in conn.exec_driver_sql("PRAGMA table_info(finances)").fetchall()
            }
            order_additions = {
                "product_name": "VARCHAR(255)",
                "quantity": "INTEGER",
                "source": "VARCHAR(30) NOT NULL DEFAULT 'manual'",
                "external_id": "VARCHAR(100)",
                "payment_status": "VARCHAR(30) NOT NULL DEFAULT 'manual'",
            }

            for name, column_type in order_additions.items():
                if name not in order_columns:
                    conn.exec_driver_sql(
                        f"ALTER TABLE orders ADD COLUMN {name} {column_type}"
                    )

            if "source_ref" not in finance_columns:
                conn.exec_driver_sql(
                    "ALTER TABLE finances ADD COLUMN source_ref VARCHAR(140)"
                )

            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_source_external_id "
                "ON orders (source, external_id)"
            )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_finances_source_ref "
                "ON finances (source_ref)"
            )
        else:
            raise RuntimeError(f"Unsupported database backend for schema updates: {backend}")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.clients import clients_bp
    from routes.products import products_bp
    from routes.orders import orders_bp
    from routes.todo import todo_bp
    from routes.finances import finances_bp
    from routes.inventory import inventory_bp
    from routes.coffee import coffee_bp
    from routes.suppliers import suppliers_bp
    from routes.distribution import distribution_bp
    from routes.offers import offers_bp
    from routes.shop_webhook import shop_webhook_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(todo_bp)
    app.register_blueprint(finances_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(coffee_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(distribution_bp)
    app.register_blueprint(offers_bp)
    app.register_blueprint(shop_webhook_bp)

    return app


app = create_app()

with app.app_context():
    db.create_all()
    ensure_additive_schema()

    # Tymczasowa naprawa istniejącej bazy na Renderze:
    # dodaje brakującą kolumnę notes do suppliers, jeśli tabela już istniała.
    try:
        with db.engine.connect() as conn:
            if db.engine.url.get_backend_name().startswith("postgresql"):
                conn.exec_driver_sql(
                    "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS notes TEXT"
                )
                conn.commit()
            else:
                columns = conn.exec_driver_sql("PRAGMA table_info(suppliers)").fetchall()
                column_names = [column[1] for column in columns]

                if "notes" not in column_names:
                    conn.exec_driver_sql("ALTER TABLE suppliers ADD COLUMN notes TEXT")
                    conn.commit()
    except Exception as error:
        print("Supplier migration skipped:", error)

if __name__ == "__main__":
    app.run(debug=True)