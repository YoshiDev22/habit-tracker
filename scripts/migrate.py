"""
Applies pending schema changes to the SQLite database.

This project has no Alembic, and create_db_and_tables() calls
SQLModel.metadata.create_all(), which creates missing TABLES but never alters
an existing one. So every column added to an existing model has to be listed
here, or the app fails at runtime with "no such column".

Safe to run as many times as you like: each entry is checked against
PRAGMA table_info and skipped when the column is already there. Adding a
column in SQLite does not rewrite the table or touch existing rows.

Deliberately depends on nothing but the standard library, so it runs with a
bare `python3` on a server where the virtualenv is not active.

Run it from the repo root, BEFORE restarting the service with the new code:

    python3 scripts/migrate.py
"""
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, "backend", ".env")

# Cada entrada es una columna que algún modelo ya declara y que una base
# existente puede no tener todavía. Se aplican en orden, y las que ya existen
# se saltan. `default` es opcional: sin él la columna nace NULL en las filas
# que ya estaban; con él, SQLite las rellena con ese valor.
MIGRATIONS = [
    {"table": "users", "column": "display_name", "type": "VARCHAR"},
    {"table": "users", "column": "first_name", "type": "VARCHAR"},
    {"table": "users", "column": "last_name", "type": "VARCHAR"},
]


def read_env_value(path, key):
    """Lee una clave de un archivo .env. Sustituye a python-dotenv, que no
    está disponible fuera del virtualenv."""
    if not os.path.exists(path):
        return None

    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()

            name, _, value = line.partition("=")
            if name.strip() != key:
                continue

            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value

    return None


def resolve_db_path():
    """Traduce DATABASE_URL a una ruta de archivo."""
    url = os.getenv("DATABASE_URL") or read_env_value(ENV_PATH, "DATABASE_URL") or "sqlite:///./habits.db"

    if not url.startswith("sqlite"):
        sys.exit(f"This script only handles SQLite databases, got: {url}")

    path = url.split("///", 1)[-1]
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(BASE_DIR, path))
    return path


def existing_columns(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def main():
    db_path = resolve_db_path()
    print(f"Database: {db_path}")

    if not os.path.exists(db_path):
        sys.exit("Not found. Nothing to migrate: the app creates it on startup.")

    connection = sqlite3.connect(db_path)
    applied = []
    try:
        for entry in MIGRATIONS:
            table, column = entry["table"], entry["column"]

            columns = existing_columns(connection, table)
            if not columns:
                sys.exit(f"No '{table}' table here. Start the app once to create the schema.")
            if column in columns:
                continue

            # Tabla, columna y tipo son constantes de este archivo, no entrada externa
            statement = f"ALTER TABLE {table} ADD COLUMN {column} {entry['type']}"
            if "default" in entry:
                statement += f" DEFAULT '{entry['default']}'"

            connection.execute(statement)
            applied.append(f"{table}.{column}")

        connection.commit()
    finally:
        connection.close()

    print("Added: " + (", ".join(applied) if applied else "nothing, already up to date"))


if __name__ == "__main__":
    main()
