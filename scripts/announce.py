"""
Publishes a notice for every account (1.26): maintenance, an outage, anything
everyone should know. Each account sees it in the bell, with the red count,
while it is current; ending it (or its end time passing) removes it from
every bell. The admin panel (BACKLOG 32) will do the same without the VPS.

Like grant_module.py, it depends on nothing but the standard library. Run it
from the repo root, with the service already running a version that has the
announcements table (1.26 or later):

    python3 scripts/announce.py --title "Mantenimiento" --body "La app se reinicia hoy a las 22:00 (5 min)." --hours 24
    python3 scripts/announce.py --list
    python3 scripts/announce.py --end 3
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from migrate import resolve_db_path  # noqa: E402

MAX_TITLE = 80
MAX_BODY = 500


def utc_now():
    # Naive UTC, like the app (utc_now_naive in backend/models.py)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fmt(value):
    return value[:16].replace("T", " ") + " UTC" if value else "until ended"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publish, list or end a notice for every account.")
    parser.add_argument("--title", help=f"short title (up to {MAX_TITLE} characters)")
    parser.add_argument("--body", default="", help=f"what to say (up to {MAX_BODY} characters)")
    parser.add_argument("--hours", type=float, help="how long it stays (from now); without it, until --end")
    parser.add_argument("--list", action="store_true", help="list the announcements")
    parser.add_argument("--end", type=int, metavar="ID", help="end an announcement now: it leaves every bell")
    args = parser.parse_args(argv)

    db_path = resolve_db_path()
    if not os.path.exists(db_path):
        print(f"No database at {db_path}.", file=sys.stderr)
        return 1
    connection = sqlite3.connect(db_path)
    try:
        if not connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='announcements'").fetchone():
            print("No 'announcements' table: restart the service on 1.26 or later first.", file=sys.stderr)
            return 1
        now = utc_now()
        if args.list:
            rows = connection.execute("SELECT id, title, created_at, ends_at FROM announcements ORDER BY id DESC").fetchall()
            if not rows:
                print("No announcements.")
            for ann_id, title, created, ends in rows:
                current = ends is None or ends > now.isoformat(sep=" ")
                print(f"#{ann_id} {'CURRENT' if current else 'ended  '} {title}  (from {fmt(created)}, {fmt(ends)})")
            return 0
        if args.end is not None:
            done = connection.execute("UPDATE announcements SET ends_at = ? WHERE id = ?",
                                      (now.isoformat(sep=" "), args.end)).rowcount
            connection.commit()
            print(f"Announcement #{args.end} ended." if done else f"No announcement #{args.end}.")
            return 0 if done else 1
        title = (args.title or "").strip()
        body = " ".join(args.body.split())
        if not title:
            parser.error("--title is required to publish")
        if len(title) > MAX_TITLE or len(body) > MAX_BODY:
            parser.error(f"title up to {MAX_TITLE} characters and body up to {MAX_BODY}")
        ends = (now + timedelta(hours=args.hours)).isoformat(sep=" ") if args.hours else None
        cursor = connection.execute("INSERT INTO announcements (title, body, created_at, ends_at) VALUES (?, ?, ?, ?)",
                                    (title, body, now.isoformat(sep=" "), ends))
        connection.commit()
        print(f"Published #{cursor.lastrowid}: {title} ({fmt(ends)}). Every account sees it in the bell.")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
