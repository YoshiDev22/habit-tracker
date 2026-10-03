"""Tapping 'Hoy' shows every time entry of the day, and lets you fix them."""
import asyncio
import datetime as dt
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

LOCAL_OFFSET_H = round(dt.datetime.now().astimezone().utcoffset().total_seconds() / 3600)
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


STATE = """({open: !document.getElementById('dayLogModal').classList.contains('hidden'),
    logOpen: !document.getElementById('logTimeModal').classList.contains('hidden'),
    date: document.getElementById('dayLogDate').textContent.replace(' ▾', ''),
    total: document.getElementById('dayLogTotal').textContent,
    next: document.getElementById('dayLogNext').disabled,
    today: document.getElementById('pomoToday').textContent,
    rows: [...document.querySelectorAll('#dayLogList .session-row')].map(r => ({
        origin: r.querySelector('.session-origin').textContent,
        when: r.querySelector('.session-when').textContent,
        detail: (r.querySelector('.session-detail') || {}).textContent || '',
        flag: r.classList.contains('session-flag')}))})"""


async def main():
    token, _ = seed()
    today = dt.date.today()
    _, tl = call("GET", "/api/tasks", expect=200)
    kanban = next(t for t in tl["tasks"] if t["title"].startswith("Revisión de idea"))
    idea = next(t for t in tl["tasks"] if t["title"] == "Idea suelta sin proyecto")

    def log(task, hour, minutes, source, note=None, day=today):
        start = dt.datetime.combine(day, dt.time(hour, 0)) - dt.timedelta(hours=LOCAL_OFFSET_H)
        call("POST", "/api/pomodoro", {
            "project_id": task["project_id"], "task_id": task["id"], "session_date": day.isoformat(),
            "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(minutes=minutes)).isoformat(),
            "duration_seconds": minutes * 60, "planned_seconds": minutes * 60, "mode": "focus",
            "was_completed": True, "source": source, "note": note,
            # Lo que manda pomodoro.js con la nota de cierre automático
            "needs_review": note == "Cerrado automáticamente a las 8 h"}, expect=201)

    # The user's case: a stopwatch left running from 01:00 that closed itself at 8 h, then 1 h today
    log(kanban, 1, 480, "stopwatch", note="Cerrado automáticamente a las 8 h")
    log(idea, 10, 60, "timer")

    b = Browser()
    await b.start()

    async def js(expr, wait=0.0):
        r = await b.js(expr)
        if wait:
            await asyncio.sleep(wait)
        return r

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.2)

        tag = await js("document.getElementById('pomoToday').tagName")
        check(tag == "BUTTON", f"'Hoy' is a button ({tag})")
        await js("document.getElementById('pomoToday').click()", wait=1.5)
        s = await js(STATE)
        months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
        check(s["open"] and s["date"] == f"Hoy, {today.day} {months[today.month - 1]}" and s["next"],
              f"opens on today, next disabled ({s['date']}, {s['next']})")
        check(s["today"] == "Hoy: 9h 0m" and s["total"] == "9h 0m · 2 registros", f"total matches 'Hoy' ({s['today']} / {s['total']})")
        check([r["when"].split(" · ")[1] for r in s["rows"]] == ["01:00–09:00", "10:00–11:00"],
              f"entries in the order they happened ({[r['when'] for r in s['rows']]})")
        f0 = s["rows"][0]
        check(f0["flag"] and f0["origin"] == "⚠" and "Revisión de idea para cambiar a kanban" in f0["detail"]
              and "Habit Tracker" in f0["detail"] and "Cerrado automáticamente" in f0["detail"],
              f"the auto-closed stopwatch is flagged, with task and project ({f0})")
        check(s["rows"][1]["detail"] == "Idea suelta sin proyecto" and not s["rows"][1]["flag"],
              f"an unassigned task shows no project ({s['rows'][1]['detail']})")
        await b.shot("day_log", full=False)

        # Fix the forgotten stopwatch: 01:00-04:00
        await js("document.querySelector('#dayLogList .session-row [data-action=edit]').click()", wait=1.2)
        s = await js(STATE)
        check(s["open"] and s["logOpen"], "✎ opens the log above the day list")
        await js("""logTimeStartEl.value = '01:00'; logTimeStartEl.dispatchEvent(new Event('input'));
            logTimeEndEl.value = '04:00'; logTimeEndEl.dispatchEvent(new Event('input'));""", wait=0.3)
        await js("logTimeSubmitBtn.click()", wait=2.5)
        s = await js(STATE)
        check(s["open"] and not s["logOpen"] and s["rows"][0]["when"].endswith("01:00–04:00 · 3h 0m"),
              f"after saving: the entry is 3h ({s['rows'][0]['when']})")
        check(s["total"] == "4h 0m · 2 registros" and s["today"] == "Hoy: 4h 0m", f"day total and 'Hoy' update ({s['total']}, {s['today']})")
        check(not s["rows"][0]["flag"] and "Cerrado automáticamente" not in s["rows"][0]["detail"],
              f"once corrected, the auto-close note and the flag go away ({s['rows'][0]})")

        # The fixture's entries are on FIXTURE_DAY (tests/ui/conftest.py moves them
        # to yesterday); the checks go there with the calendar.
        import os
        SEED_DAY = dt.date.fromisoformat(os.environ["HABIT_UI_FIXTURE_DAY"])
        pick = lambda d: f"{{ const p = document.getElementById('dayLogPicker'); p.value = '{d.isoformat()}'; p.dispatchEvent(new Event('change')); }}"

        # ‹ goes to the previous day, and › is enabled there
        await js("document.getElementById('dayLogPrev').click()", wait=1.2)
        s = await js(STATE)
        check(s["date"].startswith("Ayer, ") and not s["next"], f"‹ goes to yesterday ({s['date']})")

        # Jump to a specific day with the calendar
        arrow = await js("document.getElementById('dayLogDate').textContent.endsWith('▾')")
        await js("document.getElementById('dayLogDate').click()", wait=0.3)
        await js(pick(SEED_DAY), wait=1.2)
        s = await js(STATE)
        pk = await js("[document.getElementById('dayLogPicker').value, document.getElementById('dayLogPicker').max]")
        check(arrow and s["total"].startswith("6h 57m") and pk == [SEED_DAY.isoformat(), today.isoformat()],
              f"the date opens a calendar and jumps to the picked day ({s['date']}, {s['total']}, {pk})")
        label = s["date"]
        await js(pick(today + dt.timedelta(days=3)), wait=0.8)
        s = await js(STATE)
        check(s["date"] == label, f"a future day is ignored ({s['date']})")
        await js(pick(SEED_DAY - dt.timedelta(days=1)), wait=1.2)
        s = await js(STATE)
        check(s["total"] == "" and "Sin tiempo registrado" in await js("document.getElementById('dayLogList').textContent"),
              f"an empty day says so ({s['date']})")
        await js(pick(today), wait=1.2)

        # Delete: cancel keeps, confirm removes
        await js("document.querySelectorAll('#dayLogList .session-row [data-action=delete]')[1].click()", wait=0.6)
        await js("document.getElementById('confirmModalCancelBtn').click()", wait=0.8)
        n = len((await js(STATE))["rows"])
        await js("document.querySelectorAll('#dayLogList .session-row [data-action=delete]')[1].click()", wait=0.6)
        await js("document.getElementById('confirmModalConfirmBtn').click()", wait=2.5)
        s = await js(STATE)
        check(n == 2 and len(s["rows"]) == 1 and s["today"] == "Hoy: 3h 0m", f"delete asks first, then removes ({n} -> {len(s['rows'])}, {s['today']})")

        # Escape: log on top closes first, then the day list
        await js("document.querySelector('#dayLogList .session-row [data-action=edit]').click()", wait=1.0)
        await js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))", wait=0.4)
        s = await js(STATE)
        check(s["open"] and not s["logOpen"], "Escape closes the log, not the day list")
        await js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))", wait=0.4)
        check(not (await js(STATE))["open"], "a second Escape closes the day list")

        # An entry of an archived project can still be edited
        call("PATCH", f"/api/projects/{kanban['project_id']}", {"is_active": False}, expect=200)
        await js("loadProjects()", wait=1.5)
        await js("document.getElementById('pomoToday').click()", wait=1.5)
        await js("document.querySelector('#dayLogList .session-row [data-action=edit]').click()", wait=1.2)
        lt = await js("({open: !document.getElementById('logTimeModal').classList.contains('hidden'), project: document.getElementById('logTimeProject').textContent})")
        check(lt == {"open": True, "project": "Proyecto archivado"}, f"an archived project's entry still opens for editing ({lt})")
        await js("document.getElementById('closeLogTimeBtn').click(); closeDayLog();", wait=0.5)

        # Phone
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('pomoToday').click()", wait=1.5)
        w = await js("document.documentElement.scrollWidth")
        check(w <= 390, f"no horizontal overflow on a phone ({w}px)")
        await b.shot("day_log_mobile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_day_log():
    asyncio.run(main())
