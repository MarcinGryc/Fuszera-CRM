from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

auth_bp = Blueprint("auth", __name__)


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login"))
        return function(*args, **kwargs)

    return wrapper


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if (
            username == current_app.config["ADMIN_LOGIN"]
            and password == current_app.config["ADMIN_PASSWORD"]
        ):
            session["logged_in"] = True
            return redirect(url_for("dashboard.index"))

        error = "Nieprawidłowy login lub hasło."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))