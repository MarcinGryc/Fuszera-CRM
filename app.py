from flask import Flask
from config import Config
from extensions import db, migrate


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

    return app


app = create_app()

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)