"""
Deletes the accounts whose scheduled deletion is due ("Irme unos días" in
Mi perfil, 30 days after asking; backend/accounts.py). Everything of theirs
goes: habits, boards, tasks, time, costs, reports, modules.

It runs from the same daily systemd service as the reports
(deploy/habit-reports.service has a second ExecStart). Like
generate_reports.py it needs the app's dependencies: run it with the venv's
python, from the repo root.

    .venv/bin/python scripts/purge_accounts.py
    .venv/bin/python scripts/purge_accounts.py --dry-run
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session  # noqa: E402

from backend.accounts import due_for_purge, purge_user  # noqa: E402
from backend.database import check_pending_migrations, create_db_and_tables, engine  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Delete the accounts whose scheduled deletion is due.")
    parser.add_argument("--dry-run", action="store_true", help="list them, delete nothing")
    args = parser.parse_args(argv)

    check_pending_migrations()   # users.delete_after has to exist
    create_db_and_tables()

    with Session(engine) as session:
        due = due_for_purge(session)
        for user in due:
            label = f"account {user.id} (scheduled for {user.delete_after:%Y-%m-%d %H:%M} UTC)"
            if args.dry_run:
                print(f"would delete {label}")
                continue
            purge_user(session, user)
            print(f"deleted {label}")
    if not args.dry_run:
        print(f"{len(due)} account(s) deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
