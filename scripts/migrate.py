"""
Applies pending schema changes and data fixups to the SQLite database.

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
import unicodedata

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
    {"table": "pomodoro_sessions", "column": "source", "type": "VARCHAR", "default": "timer"},
    {"table": "users", "column": "rest_days", "type": "JSON"},
    # Nacen NULL a propósito. La tabla `statuses` todavía no existe cuando
    # esto corre (la crea create_all() al reiniciar), así que asignar el estado
    # a cada proyecto y tarea lo hace la app: ensure_user_statuses() en
    # backend/statuses.py, en el primer request de cada usuario.
    {"table": "projects", "column": "status_id", "type": "INTEGER"},
    {"table": "tasks", "column": "status_id", "type": "INTEGER"},
]

# El icono que pone el modelo cuando nadie manda uno. Un `habits.icon` con este
# valor no es una elección del usuario, así que el emoji que traiga el label
# puede quedarse con el sitio.
GENERIC_HABIT_ICON = "✅"

# Categorías Unicode de los emoji y de los símbolos que los modifican. Filtrar
# por "no es ASCII" rompería un nombre con tilde o con ñ; las letras acentuadas
# son Ll/Lu y no entran acá.
SYMBOL_CATEGORIES = {"So", "Sk"}
EMOJI_JOINERS = {"‍", "️", "⃣"}


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


def split_leading_emoji(label):
    """Separa el emoji del principio de un nombre: ("📚", "Lectura").

    Devuelve ("", label) cuando el nombre no empieza por uno."""
    cut = 0
    for char in label:
        if unicodedata.category(char) in SYMBOL_CATEGORIES or char in EMOJI_JOINERS:
            cut += 1
        else:
            break

    return label[:cut], label[cut:].lstrip()


def normalize_habit_labels(connection):
    """Saca el emoji de dentro de `habits.label` y lo deja en `habits.icon`.

    Durante meses el guardado del frontend leyó el nombre del hábito del span
    que se veía en pantalla, y ese span era "emoji + nombre". El emoji terminó
    guardado dos veces: dentro del label y en su columna. Al pintar la fila como
    icono + nombre, salía duplicado ("📚 📚 Lectura").

    Idempotente: un label ya limpio no empieza por emoji y se salta."""
    if not existing_columns(connection, "habits"):
        return []

    fixed = []
    rows = connection.execute("SELECT id, label, icon FROM habits").fetchall()
    for habit_id, label, icon in rows:
        if not label:
            continue

        emoji, name = split_leading_emoji(label)
        # Sin emoji no hay nada que mover, y si al quitarlo no queda nombre
        # (un label que era solo el emoji) se deja como está: vale más un
        # nombre raro que una fila sin nombre.
        if not emoji or not name:
            continue

        new_icon = emoji if not icon or icon == GENERIC_HABIT_ICON else icon
        connection.execute(
            "UPDATE habits SET label = ?, icon = ? WHERE id = ?",
            (name, new_icon, habit_id),
        )
        fixed.append(f"{label!r} -> icon={new_icon!r} label={name!r}")

    return fixed


def main():
    # El informe incluye nombres de hábitos, que traen emoji, y no toda consola
    # sabe codificarlos (la de Windows es cp1252 por defecto). Sin esto un print
    # tira el script DESPUÉS de haber migrado, con el commit ya hecho: el deploy
    # parecería haber fallado cuando en realidad fue bien.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

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

        # Después de las columnas: el esquema tiene que estar completo antes de
        # tocar filas.
        relabeled = normalize_habit_labels(connection)

        connection.commit()
    finally:
        connection.close()

    print("Added: " + (", ".join(applied) if applied else "nothing, already up to date"))

    if relabeled:
        print(f"Habit labels normalized ({len(relabeled)}):")
        for line in relabeled:
            print(f"  {line}")
    else:
        print("Habit labels: nothing to normalize")


if __name__ == "__main__":
    main()
