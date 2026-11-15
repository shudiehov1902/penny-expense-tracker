"""SQLite storage and one-time import of the original JSON expenses."""

import json
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app, g


class ValidationError(ValueError):
    pass


def money_to_cents(value):
    if isinstance(value, bool):
        raise ValidationError("Enter an amount greater than zero.")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= Decimal("9999999.99"):
            raise ValidationError("Amount must be between €0.01 and €9,999,999.99.")
        if amount != amount.quantize(Decimal("0.01")):
            raise ValidationError("Use no more than two decimal places.")
        return int(amount * 100)
    except (InvalidOperation, TypeError):
        raise ValidationError("Enter a valid amount, such as 12.50.") from None


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db():
    database = get_db()
    database.executescript("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            spent_on TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS expenses_date ON expenses(spent_on);
        CREATE TABLE IF NOT EXISTS budgets (
            month TEXT PRIMARY KEY,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0)
        );
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    legacy = current_app.config.get("LEGACY_FILE")
    if not legacy or database.execute("SELECT 1 FROM metadata WHERE key='legacy_import'").fetchone():
        return
    path = Path(legacy)
    if not path.exists():
        return
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise ValueError("Expected a list of expenses")
        records = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("category"), str):
                raise ValueError("An expense has no valid category")
            category = item["category"].strip()
            if not category or len(category) > 60:
                raise ValueError("An expense has an invalid category")
            records.append((category, money_to_cents(item.get("amount")), date.today().isoformat(), "Imported from the original tracker"))
    except (ValueError, OSError) as error:
        raise RuntimeError(f"Could not import {path.name}: {error}. The original file was not changed.") from error
    with database:
        database.executemany("INSERT INTO expenses(category, amount_cents, spent_on, note) VALUES (?, ?, ?, ?)", records)
        database.execute("INSERT INTO metadata(key, value) VALUES ('legacy_import', ?)", (str(path),))
