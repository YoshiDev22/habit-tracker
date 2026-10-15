"""
Quita el módulo Logros de una base: la vuelta atrás de su "migración".

Logros solo agrega tablas nuevas (las crea create_all() al arrancar; migrate.py
no tiene nada suyo) y una carpeta de archivos. Revertirlo es borrar esas tablas,
las filas de user_modules del módulo y la carpeta UPLOADS_DIR/achievements.
Ninguna tabla de otro módulo se toca.

Orden para revertir en un servidor: primero desplegar el código SIN el módulo
(si no, la app vuelve a crear las tablas vacías al reiniciar), después correr
esto. Borra datos de los usuarios para siempre: sin --yes solo dice qué haría.

Solo biblioteca estándar, como migrate.py. Desde la raíz del repo:

    python3 scripts/drop_achievements.py          # qué se borraría
    python3 scripts/drop_achievements.py --yes    # borrarlo
"""
import argparse
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from migrate import BASE_DIR, ENV_PATH, read_env_value, resolve_db_path  # noqa: E402

# De las que dependen de otras hacia las de las que dependen
TABLES = ["achievement_files", "achievements", "achievement_collections", "achievement_categories",
          "sos_actions", "sos_notes"]
MODULE = "achievements"


def uploads_folder():
    root = os.getenv("UPLOADS_DIR") or read_env_value(ENV_PATH, "UPLOADS_DIR") or os.path.join(BASE_DIR, "uploads")
    return os.path.join(os.path.abspath(root), "achievements")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true", help="borrar de verdad (sin esto, solo lo dice)")
    args = parser.parse_args(argv)

    db_path = resolve_db_path()
    if not os.path.exists(db_path):
        print(f"No existe la base {db_path}")
        return 1
    folder = uploads_folder()
    connection = sqlite3.connect(db_path)
    try:
        present = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        tables = [t for t in TABLES if t in present]
        for table in tables:
            count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            print(f"{'Borrar' if args.yes else 'Se borraría'} la tabla {table} ({count} filas)")
        if "user_modules" in present:
            count = connection.execute("SELECT COUNT(*) FROM user_modules WHERE module = ?", (MODULE,)).fetchone()[0]
            print(f"{'Borrar' if args.yes else 'Se borrarían'} {count} filas de user_modules del módulo")
        print(f"{'Borrar' if args.yes else 'Se borraría'} la carpeta {folder}"
              f"{'' if os.path.isdir(folder) else ' (no existe)'}")
        if not args.yes:
            print("Nada cambió. Para borrarlo: --yes")
            return 0
        with connection:
            for table in tables:
                connection.execute(f'DROP TABLE "{table}"')
            if "user_modules" in present:
                connection.execute("DELETE FROM user_modules WHERE module = ?", (MODULE,))
    finally:
        connection.close()
    shutil.rmtree(folder, ignore_errors=True)
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
