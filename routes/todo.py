from flask import Blueprint, redirect, render_template, request, url_for

from extensions import db
from models import Todo
from routes.auth import login_required
from routes.export_utils import export_xlsx
from routes.import_utils import read_xlsx_rows

todo_bp = Blueprint("todo", __name__)


@todo_bp.route("/todo", methods=["GET", "POST"])
@login_required
def todo():
    if request.method == "POST":
        task = request.form.get("task")
        if task:
            item = Todo(task=task, done=False)
            db.session.add(item)
            db.session.commit()
        return redirect(url_for("todo.todo"))

    todos = Todo.query.order_by(Todo.done.asc(), Todo.id.desc()).all()
    return render_template("todo.html", todos=todos)


@todo_bp.route("/todo/toggle/<int:todo_id>", methods=["POST"])
@login_required
def todo_toggle(todo_id):
    item = Todo.query.get_or_404(todo_id)
    item.done = not item.done
    db.session.commit()
    return redirect(request.referrer or url_for("todo.todo"))


@todo_bp.route("/todo/delete/<int:todo_id>", methods=["POST"])
@login_required
def todo_delete(todo_id):
    item = Todo.query.get_or_404(todo_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(request.referrer or url_for("todo.todo"))


@todo_bp.route("/todo/export")
@login_required
def todo_export():
    todos = Todo.query.order_by(Todo.done.asc(), Todo.id.desc()).all()

    rows = [[t.id, t.task, "Zrobione" if t.done else "Do zrobienia"] for t in todos]

    return export_xlsx(
        "todo.xlsx",
        [("Todo", ["ID", "Zadanie", "Status"], rows)],
    )

@todo_bp.route("/todo/import", methods=["POST"])
@login_required
def todo_import():
    file = request.files.get("file")

    if not file:
        return redirect(url_for("todo.todo"))

    rows = read_xlsx_rows(file)

    for row in rows:
        status = str(row.get("Status", "")).lower()

        item = Todo(
            task=row.get("Zadanie") or row.get("Task") or "Bez nazwy",
            done=True if "zrob" in status else False,
        )

        db.session.add(item)

    db.session.commit()

    return redirect(url_for("todo.todo"))