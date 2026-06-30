from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "zmien-to-na-dlugi-losowy-sekretny-tekst"

DB_NAME = "crm.db"

ADMIN_LOGIN = "ziomeczki@fuszera.pl"
ADMIN_PASSWORD = "Fuszera_2023@"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(conn, table_name, column_name, column_definition):
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing_columns = [column["name"] for column in columns]

    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT DEFAULT 'individual',
            name TEXT NOT NULL,
            company TEXT,
            nip TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            notes TEXT
        )
    """)

    add_column_if_missing(conn, "clients", "type", "TEXT DEFAULT 'individual'")
    add_column_if_missing(conn, "clients", "company", "TEXT")
    add_column_if_missing(conn, "clients", "nip", "TEXT")
    add_column_if_missing(conn, "clients", "email", "TEXT")
    add_column_if_missing(conn, "clients", "phone", "TEXT")
    add_column_if_missing(conn, "clients", "address", "TEXT")
    add_column_if_missing(conn, "clients", "notes", "TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            weight TEXT,
            price REAL NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            order_date TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS finances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            unit TEXT DEFAULT 'szt',
            notes TEXT
        )
    """)

    conn.commit()
    conn.close()


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        if request.form.get("username") == ADMIN_LOGIN and request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))

        error = "Nieprawidłowy login lub hasło."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    conn = get_db()

    income = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM finances WHERE type='income'").fetchone()[0]
    expense = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM finances WHERE type='expense'").fetchone()[0]
    balance = income - expense

    individual_count = conn.execute("SELECT COUNT(*) FROM clients WHERE type='individual'").fetchone()[0]
    b2b_count = conn.execute("SELECT COUNT(*) FROM clients WHERE type='b2b'").fetchone()[0]

    products_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    orders_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    inventory_count = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]

    todos = conn.execute("SELECT * FROM todos WHERE done=0 ORDER BY id DESC LIMIT 8").fetchall()
    todos_count = conn.execute("SELECT COUNT(*) FROM todos WHERE done=0").fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        income=income,
        expense=expense,
        balance=balance,
        individual_count=individual_count,
        b2b_count=b2b_count,
        products_count=products_count,
        orders_count=orders_count,
        inventory_count=inventory_count,
        todos=todos,
        todos_count=todos_count,
    )


@app.route("/clients", methods=["GET", "POST"])
@login_required
def clients():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO clients (type, name, company, nip, email, phone, address, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("type"),
            request.form.get("name"),
            request.form.get("company"),
            request.form.get("nip"),
            request.form.get("email"),
            request.form.get("phone"),
            request.form.get("address"),
            request.form.get("notes"),
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("clients"))

    b2b = conn.execute("SELECT * FROM clients WHERE type='b2b' ORDER BY id DESC").fetchall()
    individual = conn.execute("SELECT * FROM clients WHERE type='individual' ORDER BY id DESC").fetchall()

    conn.close()
    return render_template("clients.html", b2b=b2b, individual=individual)


@app.route("/clients/edit/<int:client_id>", methods=["GET", "POST"])
@login_required
def client_edit(client_id):
    conn = get_db()

    client = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()

    if request.method == "POST":
        conn.execute("""
            UPDATE clients
            SET type=?, name=?, company=?, nip=?, email=?, phone=?, address=?, notes=?
            WHERE id=?
        """, (
            request.form.get("type"),
            request.form.get("name"),
            request.form.get("company"),
            request.form.get("nip"),
            request.form.get("email"),
            request.form.get("phone"),
            request.form.get("address"),
            request.form.get("notes"),
            client_id,
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("clients"))

    conn.close()
    return render_template("client_edit.html", client=client)


@app.route("/clients/delete/<int:client_id>", methods=["POST"])
@login_required
def client_delete(client_id):
    conn = get_db()
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("clients"))


@app.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    conn = get_db()
    client = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    orders = conn.execute("""
        SELECT * FROM orders
        WHERE client_id=?
        ORDER BY order_date DESC, id DESC
    """, (client_id,)).fetchall()
    conn.close()
    return render_template("client_detail.html", client=client, orders=orders)


@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO products (name, weight, price)
            VALUES (?, ?, ?)
        """, (
            request.form.get("name"),
            request.form.get("weight"),
            float(request.form.get("price")),
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("products"))

    products_list = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("products.html", products=products_list)


@app.route("/products/delete/<int:product_id>", methods=["POST"])
@login_required
def product_delete(product_id):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("products"))


@app.route("/orders", methods=["GET", "POST"])
@login_required
def orders():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO orders (client_id, product_name, quantity, total, order_date, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("client_id") or None,
            request.form.get("product_name"),
            int(request.form.get("quantity")),
            float(request.form.get("total")),
            request.form.get("order_date") or datetime.now().strftime("%Y-%m-%d"),
            request.form.get("notes"),
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("orders"))

    orders_list = conn.execute("""
        SELECT orders.*, clients.name AS client_name, clients.company AS client_company
        FROM orders
        LEFT JOIN clients ON orders.client_id = clients.id
        ORDER BY orders.order_date DESC, orders.id DESC
    """).fetchall()

    clients_list = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    products_list = conn.execute("SELECT * FROM products ORDER BY name").fetchall()

    conn.close()

    return render_template("orders.html", orders=orders_list, clients=clients_list, products=products_list)


@app.route("/orders/delete/<int:order_id>", methods=["POST"])
@login_required
def order_delete(order_id):
    conn = get_db()
    conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("orders"))


@app.route("/todo", methods=["GET", "POST"])
@login_required
def todo():
    conn = get_db()

    if request.method == "POST":
        task = request.form.get("task")
        if task:
            conn.execute("INSERT INTO todos (task, done) VALUES (?, 0)", (task,))
            conn.commit()

        conn.close()
        return redirect(url_for("todo"))

    todos = conn.execute("SELECT * FROM todos ORDER BY done ASC, id DESC").fetchall()
    conn.close()
    return render_template("todo.html", todos=todos)


@app.route("/todo/toggle/<int:todo_id>", methods=["POST"])
@login_required
def todo_toggle(todo_id):
    conn = get_db()
    todo_item = conn.execute("SELECT done FROM todos WHERE id=?", (todo_id,)).fetchone()

    if todo_item:
        new_status = 0 if todo_item["done"] else 1
        conn.execute("UPDATE todos SET done=? WHERE id=?", (new_status, todo_id))
        conn.commit()

    conn.close()
    return redirect(request.referrer or url_for("todo"))


@app.route("/todo/delete/<int:todo_id>", methods=["POST"])
@login_required
def todo_delete(todo_id):
    conn = get_db()
    conn.execute("DELETE FROM todos WHERE id=?", (todo_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("todo"))


@app.route("/finances", methods=["GET", "POST"])
@login_required
def finances():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO finances (type, title, amount, date)
            VALUES (?, ?, ?, ?)
        """, (
            request.form.get("type"),
            request.form.get("title"),
            float(request.form.get("amount")),
            request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("finances"))

    items = conn.execute("SELECT * FROM finances ORDER BY date DESC, id DESC").fetchall()
    income = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM finances WHERE type='income'").fetchone()[0]
    expense = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM finances WHERE type='expense'").fetchone()[0]
    balance = income - expense

    conn.close()
    return render_template("finances.html", items=items, income=income, expense=expense, balance=balance)


@app.route("/finances/delete/<int:item_id>", methods=["POST"])
@login_required
def finance_delete(item_id):
    conn = get_db()
    conn.execute("DELETE FROM finances WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("finances"))


@app.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO inventory (name, quantity, unit, notes)
            VALUES (?, ?, ?, ?)
        """, (
            request.form.get("name"),
            float(request.form.get("quantity") or 0),
            request.form.get("unit") or "szt",
            request.form.get("notes"),
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("inventory"))

    items = conn.execute("SELECT * FROM inventory ORDER BY name").fetchall()
    conn.close()
    return render_template("inventory.html", items=items)


@app.route("/inventory/update/<int:item_id>", methods=["POST"])
@login_required
def inventory_update(item_id):
    conn = get_db()
    conn.execute("""
        UPDATE inventory
        SET quantity=?
        WHERE id=?
    """, (
        float(request.form.get("quantity") or 0),
        item_id,
    ))
    conn.commit()
    conn.close()
    return redirect(url_for("inventory"))


@app.route("/inventory/delete/<int:item_id>", methods=["POST"])
@login_required
def inventory_delete(item_id):
    conn = get_db()
    conn.execute("DELETE FROM inventory WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("inventory"))


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


@app.route("/coffee-pricing", methods=["GET", "POST"])
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
            "b2c_250": calculate_price(green_price, 0.25, labor, 0.65, 0),
            "b2c_1000": calculate_price(green_price, 1.0, labor, 0.65, 0),
            "b2b_250": calculate_price(green_price, 0.25, labor, 0.45, 0.20),
            "b2b_1000": calculate_price(green_price, 1.0, labor, 0.45, 0.20),
        }

    return render_template("coffee_pricing.html", result=result)


init_db()

if __name__ == "__main__":
    app.run(debug=True)