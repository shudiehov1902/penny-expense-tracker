# Penny

A local personal expense tracker built with Python, Flask, SQLite and a responsive web interface. Amounts are in EUR.

## Features

- Add, edit and delete expenses with a date, category and optional note.
- Monthly overview with total spending, category breakdown and daily activity.
- Separate budgets for each month, with remaining and over-budget balances.
- Search by category or note, filter categories and sort transactions.
- Export the selected month's transactions as CSV.
- Store money as integer cents; validate amounts and dates on the server.
- Import the original JSON expenses once, without modifying the source file.
- English interface, keyboard-accessible forms and responsive layouts.

## Run locally

Python 3.11 or newer is recommended. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Open **http://127.0.0.1:5050** in a browser. In PyCharm, choose the project's `.venv` interpreter and run `main.py`.

The app binds to loopback only. It is a single-user local application; it does not provide login, cloud synchronization or shared accounts. The included development server is intended for local use.

## Data and migration

The database is created at `data/penny.sqlite3`. Back up this file while the application is stopped. To choose another database, set `PENNY_DATABASE`; to change the port, set `PORT`.

On first launch, if `practice_expenses.json` exists, the app imports its records in one transaction and records that the import has finished. Subsequent launches do not import them again. The original JSON file is never rewritten. Original records do not have dates: they receive the local date of import and the note “Imported from the original tracker”. Existing category labels are preserved.

Deleting the database resets the import marker, so a new database will import that JSON again if it still exists. Budgets are stored per month. CSV export includes the full selected month, independent of table search or category filters.

Personal JSON and SQLite data are excluded from Git. Do not commit your real expenses. For a demo, use an empty database or enter fictional records manually.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use temporary databases and never touch personal expense data. They cover persistence, validation, money precision, budgets, migration, CSV export and local write protection.

## Project structure

```text
main.py                     Local launcher
tracker/__init__.py         Flask app factory and HTTP routes
tracker/db.py               SQLite storage, validation and JSON migration
tracker/templates/index.html
tracker/static/style.css
tracker/static/app.js        Interface and API requests
tests/test_app.py
requirements.txt
requirements-dev.txt
```

The unrelated Python learning exercises have been removed from the application. The original source was backed up before the refactor.

## Learning roadmap

1. Explain the path from a form submission to a validated SQLite record.
2. Add a feature independently, such as a category-specific budget or CSV import.
3. Add tests, screenshots and a short demo recording before publishing on GitHub.
4. Complete at least one project per month, with a working result and a clear README.

## Next versions

- CSV import with a preview and duplicate handling.
- Recurring expenses.
- Category management and category-specific budgets.
- Account authentication and a production deployment, if shared access is needed.
