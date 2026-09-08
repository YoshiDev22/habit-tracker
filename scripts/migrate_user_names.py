"""
Adds the optional profile columns to the users table: display_name,
first_name and last_name.

This project has no Alembic, and create_db_and_tables() calls
SQLModel.metadata.create_all(), which only creates missing tables and never
alters an existing one. So a database that already has a users table needs
this script, or every query will fail with "no such column: users.display_name".

Safe to run more than once: it only adds the columns that are missing, and
adding a nullable column in SQLite does not rewrite the table or touch any
existing row.

Run it from the repo root, BEFORE deploying the code that uses the columns:

    python scripts/migrate_user_names.py
"""
import os
import sqlite3
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, "backend", ".env"))

NEW_COLUMNS = {
    "display_name": "VARCHAR",
    "first_name": "VARCHAR",
    "last_name": "VARCHAR",
}


def resolve_db_path():
    """Traduce DATABASE_URL a una ruta de archivo"""
    url = os.getenv("DATABASE_URL", "sqlite:///./habits.db")

    if not url.startswith("sqlite"):
        sys.exit(f"This script only handles SQLite databases, got: {url}")

    path = url.split("///", 1)[-1]
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(BASE_DIR, path))
    return path


def main():
    db_path = resolve_db_path()
    print(f"Database: {db_path}")

    if not os.path.exists(db_path):
        sys.exit("Not found. Nothing to migrate: the app creates it on startup.")

    connection = sqlite3.connect(db_path)
    try:
        existing = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if not existing:
            sys.exit("No 'users' table here. Start the app once to create the schema.")

        added = []
        for column, sql_type in NEW_COLUMNS.items():
            if column in existing:
                continue
            # Los nombres de columna son constantes de este archivo, no entrada externa
            connection.execute(f"ALTER TABLE users ADD COLUMN {column} {sql_type}")
            added.append(column)

        connection.commit()
    finally:
        connection.close()

    print("Added: " + (", ".join(added) if added else "nothing, already up to date"))


if __name__ == "__main__":
    main()
