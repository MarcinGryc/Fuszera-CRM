from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)
DB_NAME = "crm.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT,
            email TEXT,
            phone TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/clients")
def clients():
    conn = get_db()
    clients = conn.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("clients.html", clients=clients)


@app.route("/clients/new", methods=["GET", "POST"])
def client_new():
    if request.method == "POST":
        name = request.form.get("name")
        company = request.form.get("company")
        email = request.form.get("email")
        phone = request.form.get("phone")
        notes = request.form.get("notes")

        conn = get_db()
        conn.execute(
            """
            INSERT INTO clients (name, company, email, phone, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, company, email, phone, notes)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("clients"))

    return render_template("client_new.html")


init_db()

if __name__ == "__main__":
    app.run(debug=True)