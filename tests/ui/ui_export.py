"""Reportes: 'Exportar CSV' downloads the range's time entries."""
import asyncio
import csv
import datetime as dt
import io
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

LOCAL_OFFSET_H = round(dt.datetime.now().astimezone().utcoffset().total_seconds() / 3600)
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    token, _ = seed()
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    # A tricky task: formula-like title; a note with comma and quotes. It carries
    # a tag itself: the fixture's tagged sessions are from yesterday, which on a
    # Monday falls in the previous week, outside the exported range.
    _, tags = call("GET", "/api/tags", expect=200)
    doc = next(t for t in tags["tags"] if t["name"] == "documentación")
    _, evil = call("POST", "/api/tasks", {"title": "=HYPERLINK(\"x\")", "tag_ids": [doc["id"]]}, expect=201)
    start = dt.datetime.combine(monday, dt.time(9, 0)) - dt.timedelta(hours=LOCAL_OFFSET_H)
    call("POST", "/api/pomodoro", {
        "project_id": evil["project_id"], "task_id": evil["id"], "session_date": monday.isoformat(),
        "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(minutes=90)).isoformat(),
        "duration_seconds": 5400, "planned_seconds": 5400, "mode": "focus", "was_completed": True,
        "source": "manual", "note": 'Leí "docs", y notas'}, expect=201)
    _, ws = call("GET", f"/api/pomodoro?date_from={monday}&date_to={monday + dt.timedelta(days=6)}", expect=200)
    focus = [s for s in ws["sessions"] if s["mode"] == "focus"]

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
        await b.js("window.__csv = null; downloadText = (name, text, type) => { window.__csv = {name, text, type}; };")
        await b.js("document.getElementById('reportsExport').click()")
        await asyncio.sleep(2.0)
        got = await b.js("window.__csv")
        check(got is not None and got["name"] == f"habit-tracker-tiempo_{monday}_{monday + dt.timedelta(days=6)}.csv",
              f"downloads a file named after the range ({got and got['name']})")
        text = got["text"]
        check(text.startswith("﻿"), "starts with a UTF-8 BOM for Excel")
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
        header, body = rows[0], rows[1:]
        check(header == ["Fecha", "Inicio", "Fin", "Duración", "Horas", "Tarea", "Proyecto", "Etiquetas", "Origen", "Nota"],
              f"header ({header})")
        check(len(body) == len(focus), f"one row per focus entry ({len(body)} / {len(focus)})")
        hours = round(sum(float(r[4]) for r in body), 2)
        check(abs(hours - sum(s["duration_seconds"] for s in focus) / 3600) < 0.02, f"hours add up ({hours})")
        mine = next(r for r in body if r[9].startswith("Leí"))
        check(mine[0] == monday.isoformat() and mine[1] == "09:00" and mine[2] == "10:30" and mine[3] == "1:30"
              and mine[4] == "1.50" and mine[8] == "Registrado a mano", f"times, duration and origin ({mine})")
        check(mine[5] == "'=HYPERLINK(\"x\")", f"a formula-like title is neutralized ({mine[5]})")
        check(mine[9] == 'Leí "docs", y notas' and mine[6] == "Sin asignar", f"quotes and commas survive ({mine[9]}, {mine[6]})")
        tagged = [r for r in body if r[7]]
        check(any("documentación" in r[7] for r in tagged), f"tags are listed ({[r[7] for r in tagged][:2]})")
        check(body == sorted(body, key=lambda r: (r[0], r[1])), "rows in chronological order")

        # An empty range says so instead of downloading an empty file
        await b.js("window.__csv = null; document.getElementById('reportsPrev').click()")
        await asyncio.sleep(0.3)
        await b.js("document.getElementById('reportsPrev').click()")
        await asyncio.sleep(1.2)
        await b.js("document.getElementById('reportsExport').click()")
        await asyncio.sleep(1.2)
        r = await b.js("({csv: window.__csv, label: document.getElementById('reportsExport').textContent})")
        check(r["csv"] is None and r["label"] == "Sin registros en este periodo", f"empty range: no file, a message ({r['label']})")
        await b.shot("reports_export", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_export():
    asyncio.run(main())
