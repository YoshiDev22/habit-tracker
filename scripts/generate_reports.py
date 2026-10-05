"""
Generates the automatic weekly and monthly reports (épica 30, Fase 4).

For every active account, in its own local date: on Monday the report of the
previous week (Monday to Sunday), on day 1 the one of the previous month. It
also catches up on periods missed while the server was down (4 weeks, 2
months back), skips periods with no time logged, and redoes a report that
was generated halfway through its period. Running it twice creates nothing
new: there is one report per account, kind and period.

It runs outside uvicorn, from a systemd timer (deploy/habit-reports.timer):
inside the app, restarts or several workers would fire it twice. Unlike
migrate.py it needs the app's dependencies, so run it with the venv's
python, from the repo root (DATABASE_URL may be relative to it):

    .venv/bin/python scripts/generate_reports.py
    .venv/bin/python scripts/generate_reports.py --dry-run
    .venv/bin/python scripts/generate_reports.py --email someone@example.com --today 2026-10-12
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select  # noqa: E402

from backend.database import check_pending_migrations, create_db_and_tables, engine  # noqa: E402
from backend.models import User  # noqa: E402
from backend.reports import generate_report, local_today, missing_reports  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate the automatic weekly and monthly reports.")
    parser.add_argument("--dry-run", action="store_true", help="list what would be generated, save nothing")
    parser.add_argument("--email", help="only this account")
    parser.add_argument("--today", type=date.fromisoformat,
                        help="pretend today is this date (YYYY-MM-DD) instead of each account's local date")
    args = parser.parse_args(argv)

    # Same guard as the app: never write to a database that still needs migrate.py
    check_pending_migrations()
    create_db_and_tables()   # the reports table, if the service hasn't restarted yet

    made = failed = 0
    with Session(engine) as session:
        # Sin las que se van: con el borrado programado no se les generan reportes
        query = select(User).where(User.is_active == True, User.delete_after.is_(None))  # noqa: E712
        if args.email:
            query = query.where(User.email == args.email)
        users = session.exec(query.order_by(User.id)).all()
        if args.email and not users:
            print(f"No active account with email {args.email}.", file=sys.stderr)
            return 1
        for user in users:
            today = args.today or local_today(session, user)
            for kind, start in missing_reports(session, user, today):
                label = f"{user.email}: {kind} from {start.isoformat()}"
                if args.dry_run:
                    print(f"would generate {label}")
                    continue
                try:
                    generate_report(session, user, kind, start, today, trigger="auto")
                except Exception as error:  # one account failing must not stop the others
                    session.rollback()
                    print(f"FAILED {label}: {error}", file=sys.stderr)
                    failed += 1
                    continue
                made += 1
                print(f"generated {label}")
    if not args.dry_run:
        print(f"{made} report(s) generated.")
    # Non-zero so systemd marks the run as failed and it shows in the journal
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
