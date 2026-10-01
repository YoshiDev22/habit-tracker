"""
Gives or removes an account's access to a module (backend/modules.py).

The maker plan is free but, for now, only for the accounts given access
here. Access is not a preference: the user turns the module on or off in
Mi perfil once they have it. Removing access turns it off without touching
what the user chose, so giving it back restores it as it was.

Like migrate.py, it depends on nothing but the standard library. Run it from
the repo root, with the service already running the version that has the
user_modules table:

    python3 scripts/grant_module.py --email someone@example.com --module maker
    python3 scripts/grant_module.py --email someone@example.com --module maker --revoke
    python3 scripts/grant_module.py --list
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrate import resolve_db_path  # noqa: E402
from backend.modules import MODULES  # noqa: E402


def list_access(connection):
    rows = connection.execute(
        "SELECT users.email, user_modules.module, user_modules.allowed, user_modules.enabled "
        "FROM user_modules JOIN users ON users.id = user_modules.user_id "
        "WHERE user_modules.allowed IS NOT NULL ORDER BY user_modules.module, users.email"
    ).fetchall()
    if not rows:
        print("No account has a module access set.")
    for email, module, allowed, enabled in rows:
        state = "access" if allowed else "no access"
        choice = {None: "default", 1: "on", 0: "off"}[enabled]
        print(f"{module:8} {email}  ({state}, user choice: {choice})")


def set_access(connection, email, module, allowed):
    user = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if user is None:
        sys.exit(f"No account with email {email}.")
    connection.execute(
        "INSERT INTO user_modules (user_id, module, allowed) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, module) DO UPDATE SET allowed = excluded.allowed",
        (user[0], module, int(allowed)),
    )
    connection.commit()
    print(f"{email}: {'access given to' if allowed else 'access removed from'} '{module}'.")


def main():
    parser = argparse.ArgumentParser(description="Give or remove an account's access to a module.")
    parser.add_argument("--email", help="the account's email")
    parser.add_argument("--module", choices=sorted(MODULES), help="the module")
    parser.add_argument("--revoke", action="store_true", help="remove the access instead of giving it")
    parser.add_argument("--list", action="store_true", help="list the accounts with an access set")
    args = parser.parse_args()
    if not args.list and not (args.email and args.module):
        parser.error("use --email and --module, or --list")

    db_path = resolve_db_path()
    if not os.path.exists(db_path):
        sys.exit(f"Database not found: {db_path}")

    connection = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "user_modules" not in tables:
            sys.exit("No 'user_modules' table yet. Restart the service with the new version first: it creates it.")
        if args.list:
            list_access(connection)
        else:
            set_access(connection, args.email, args.module, not args.revoke)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
