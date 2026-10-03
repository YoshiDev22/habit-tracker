"""Reportes: '⬇ Hábitos CSV' downloads one row per day and habit of the range."""
import asyncio
import csv
import datetime as dt
import io
import json

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    token, _ = seed()
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    # Two habits, one with a formula-like name; this week's Monday done for both
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "icon": "💪"}, expect=201)
    call("POST", "/api/habits/definitions", {"key": "formula", "label": "=SUMA(1)"}, expect=201)
    call("POST", "/api/habits", {"date": monday.isoformat(), "habits": {"gym": True, "formula": True}}, expect=200)
    days = (today - monday).days + 1   # the week up to today

    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(1.5)
        st = await b.js("""({time: document.getElementById('reportsExport').textContent,
            habits: document.getElementById('reportsExportHabits').textContent,
            shown: !document.getElementById('reportsExportHabits').hidden})""")
        check(st == {"time": "⬇ Tiempo CSV", "habits": "⬇ Hábitos CSV", "shown": True},
              f"two export links under the range ({st})")

        await b.js("window.__csv = null; downloadText = (name, text, type) => { window.__csv = {name, text, type}; };")
        await b.js("document.getElementById('reportsExportHabits').click()")
        await b.wait_for("window.__csv !== null")
        got = await b.js("window.__csv")
        check(got["name"] == f"habit-tracker-habitos_{monday}_{monday + dt.timedelta(days=6)}.csv",
              f"file named after the range ({got['name']})")
        text = got["text"]
        check(text.startswith("﻿"), "starts with a UTF-8 BOM for Excel")
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
        header, body = rows[0], rows[1:]
        check(header == ["Fecha", "Día", "Hábito", "Hecho", "Tipo de día"], f"header ({header})")
        check(len(body) == days * 2, f"one row per day up to today and habit ({len(body)} / {days * 2})")
        first = {r[2]: r for r in body if r[0] == monday.isoformat()}
        check(first.get("💪 Gym", [None] * 5)[1:4] == ["Lun", "💪 Gym", "Sí"], f"Monday's gym is done ({first})")
        check("'=SUMA(1)" in first and first["'=SUMA(1)"][3] == "Sí", "a formula-like habit name is neutralized")
        today_rows = [r for r in body if r[0] == today.isoformat()]
        check(all(r[4] == "Hoy (en curso)" for r in today_rows), f"today is marked in progress ({today_rows})")

        # With the habits module off, the link goes away
        call("PUT", "/api/auth/me/modules/habits", {"enabled": False}, expect=200)
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(1.0)
        check(await b.js("document.getElementById('reportsExportHabits').hidden"), "hidden with the habits module off")
        call("PUT", "/api/auth/me/modules/habits", {"enabled": True}, expect=200)
        await b.shot("reports_export_habits", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_export_habits():
    asyncio.run(main())
