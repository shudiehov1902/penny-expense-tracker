"""Penny: a local, single-user expense tracker."""

import csv
import io
import os
import secrets
from datetime import date
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from .db import ValidationError, close_db, get_db, init_db, money_to_cents

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATEGORIES = ["Food & drinks", "Groceries", "Transport", "Shopping", "Home", "Health", "Entertainment", "Travel", "Education", "Other"]


def validate_month(value):
    try:
        parsed = date.fromisoformat(value + "-01")
        if parsed.strftime("%Y-%m") != value:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError("Choose a valid month.") from None
    return value


def validate_expense(data):
    if not isinstance(data, dict):
        raise ValidationError("Expected an expense object.")
    category, note = data.get("category", ""), data.get("note", "")
    if not isinstance(category, str) or not 1 <= len(category.strip()) <= 60:
        raise ValidationError("Category must contain 1–60 characters.")
    if not isinstance(note, str) or len(note.strip()) > 240:
        raise ValidationError("Note must contain no more than 240 characters.")
    spent_on = data.get("spent_on", "")
    try:
        parsed = date.fromisoformat(spent_on)
        if parsed.isoformat() != spent_on:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError("Choose a valid expense date.") from None
    return category.strip(), money_to_cents(data.get("amount")), spent_on, note.strip()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("PENNY_DATABASE", str(ROOT / "data" / "penny.sqlite3")),
        LEGACY_FILE=str(ROOT / "practice_expenses.json"),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    token = secrets.token_urlsafe(32)
    with app.app_context():
        init_db()

    @app.before_request
    def protect_local_writes():
        if request.method in {"POST", "PUT", "DELETE", "PATCH"} and request.headers.get("X-Penny-Token") != token:
            return jsonify(error="Refresh the page and try again."), 403

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'"
        return response

    @app.errorhandler(ValidationError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(400)
    def bad_request(_error):
        return jsonify(error="Send valid JSON data."), 400

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="This request is too large."), 413

    @app.get("/")
    def index():
        return render_template("index.html", token=token)

    @app.get("/api/overview")
    def overview():
        month = validate_month(request.args.get("month", date.today().strftime("%Y-%m")))
        database = get_db()
        records = [dict(row) for row in database.execute(
            "SELECT id, category, amount_cents, spent_on, note FROM expenses WHERE substr(spent_on, 1, 7)=? ORDER BY spent_on DESC, id DESC", (month,)
        )]
        total = sum(row["amount_cents"] for row in records)
        grouped, days = {}, {}
        for row in records:
            grouped[row["category"]] = grouped.get(row["category"], 0) + row["amount_cents"]
            days[row["spent_on"]] = days.get(row["spent_on"], 0) + row["amount_cents"]
        budget = database.execute("SELECT amount_cents FROM budgets WHERE month=?", (month,)).fetchone()
        categories = sorted(set(DEFAULT_CATEGORIES) | {r[0] for r in database.execute("SELECT DISTINCT category FROM expenses")}, key=str.casefold)
        return jsonify(month=month, expenses=records, total_cents=total,
                       budget_cents=budget[0] if budget else None,
                       categories=categories,
                       breakdown=[{"category":k,"amount_cents":v} for k,v in sorted(grouped.items(), key=lambda item:item[1], reverse=True)],
                       daily=[{"date":k,"amount_cents":v} for k,v in sorted(days.items())])

    @app.post("/api/expenses")
    def add():
        values = validate_expense(request.get_json())
        database = get_db()
        with database:
            cursor = database.execute("INSERT INTO expenses(category, amount_cents, spent_on, note) VALUES (?, ?, ?, ?)", values)
        return jsonify(id=cursor.lastrowid), 201

    @app.put("/api/expenses/<int:expense_id>")
    def edit(expense_id):
        values = validate_expense(request.get_json())
        database = get_db()
        with database:
            cursor = database.execute("UPDATE expenses SET category=?, amount_cents=?, spent_on=?, note=? WHERE id=?", (*values, expense_id))
        if not cursor.rowcount:
            return jsonify(error="Expense not found."), 404
        return jsonify(ok=True)

    @app.delete("/api/expenses/<int:expense_id>")
    def delete(expense_id):
        database = get_db()
        with database:
            cursor = database.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        if not cursor.rowcount:
            return jsonify(error="Expense not found."), 404
        return jsonify(ok=True)

    @app.put("/api/budget")
    def budget():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValidationError("Expected a budget object.")
        month = validate_month(data.get("month", ""))
        amount = data.get("amount")
        database = get_db()
        with database:
            if amount is None or amount == "":
                database.execute("DELETE FROM budgets WHERE month=?", (month,))
            else:
                cents = money_to_cents(amount)
                database.execute("INSERT INTO budgets(month, amount_cents) VALUES (?, ?) ON CONFLICT(month) DO UPDATE SET amount_cents=excluded.amount_cents", (month, cents))
        return jsonify(ok=True)

    @app.get("/api/export")
    def export():
        month = validate_month(request.args.get("month", date.today().strftime("%Y-%m")))
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Date", "Category", "Amount (EUR)", "Note"])
        def safe_cell(value):
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        for row in get_db().execute("SELECT * FROM expenses WHERE substr(spent_on, 1, 7)=? ORDER BY spent_on DESC, id DESC", (month,)):
            writer.writerow([row["spent_on"], safe_cell(row["category"]), f'{row["amount_cents"] / 100:.2f}', safe_cell(row["note"])])
        return Response("\ufeff" + output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="penny-{month}.csv"'})

    return app
