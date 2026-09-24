"""Editing a time entry offers every open task, and moving it moves its project too."""
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


async def main():
    token, _ = seed()
    today = dt.date.today()
    _, tl = call("GET", "/api/tasks", expect=200)
    kanban = next(t for t in tl["tasks"] if t["title"].startswith("Revisión de idea"))      # Habit Tracker
    idea = next(t for t in tl["tasks"] if t["title"] == "Idea suelta sin proyecto")         # Sin asignar
    start = dt.datetime.combine(today, dt.time(9, 0)) - dt.timedelta(hours=LOCAL_OFFSET_H)

    def body(task, project_id):
        return {"project_id": project_id, "task_id": task["id"], "session_date": today.isoformat(),
                "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(minutes=40)).isoformat(),
                "duration_seconds": 2400, "planned_seconds": 2400, "mode": "focus", "was_completed": True, "source": "manual"}

    # API: the task decides the project, on create and on edit
    _, s1 = call("POST", "/api/pomodoro", body(idea, kanban["project_id"]), expect=201)
    check(s1["project_id"] == idea["project_id"], f"POST: a wrong project_id is replaced by the task's ({s1['project_id']} / {idea['project_id']})")
    _, s2 = call("PATCH", f"/api/pomodoro/{s1['id']}", {"task_id": kanban["id"]}, expect=200)
    check(s2["task_id"] == kanban["id"] and s2["project_id"] == kanban["project_id"],
          f"PATCH: moving to a task of another project moves the project ({s2['project_id']})")
    call("PATCH", f"/api/pomodoro/{s1['id']}", {"task_id": idea["id"]}, expect=200)   # back, for the UI part

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
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        await js("document.getElementById('pomoToday').click()", wait=1.5)
        row = f"[...document.querySelectorAll('#dayLogList .session-row')].find(r => r.dataset.sessionId === '{s1['id']}')"
        await js(f"{row}.querySelector('[data-action=edit]').click()", wait=1.5)
        st = await js("""({selected: logTimeTaskEl.selectedOptions[0].textContent,
            groups: [...logTimeTaskEl.querySelectorAll('optgroup')].map(g => [g.label, g.children.length]),
            options: [...logTimeTaskEl.options].map(o => o.textContent),
            project: document.getElementById('logTimeProject').textContent})""")
        check(st["selected"] == idea["title"] and st["project"] == "Sin asignar", f"opens on its task and project ({st['selected']}, {st['project']})")
        check(len(st["groups"]) >= 2 and "Habit Tracker" in [g[0] for g in st["groups"]] and kanban["title"] in st["options"],
              f"lists the open tasks of every project, grouped ({st['groups']})")
        check(st["groups"][0][0] == "Sin asignar", f"the entry's own project goes first ({st['groups'][0]})")
        await b.shot("logtime_tasks", full=False)

        # Pick a task of another project: the header follows; saving moves the entry
        await js(f"logTimeTaskEl.value = '{kanban['id']}'; logTimeTaskEl.dispatchEvent(new Event('change'))", wait=0.3)
        header = await js("document.getElementById('logTimeProject').textContent")
        check(header == "Habit Tracker", f"the header shows the new task's project ({header})")
        await js("logTimeSubmitBtn.click()", wait=2.5)
        _, ss = call("GET", f"/api/pomodoro?task_id={kanban['id']}", expect=200)
        moved = next((x for x in ss["sessions"] if x["id"] == s1["id"]), None)
        check(moved is not None and moved["project_id"] == kanban["project_id"], f"saved on the new task and project ({moved and moved['project_id']})")
        detail = await js(f"{row}.querySelector('.session-detail').textContent")
        check(kanban["title"] in detail and "Habit Tracker" in detail, f"the day list shows it moved ({detail})")

        # Registering from a card still preselects that card's task
        await js("closeDayLog()", wait=0.3)
        await js("[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Revisión de idea')).click()", wait=1.2)
        await js("document.querySelector('#cardTimer [data-timer=manual]').click()", wait=1.5)
        pre = await js("[logTimeTaskEl.selectedOptions[0].textContent, document.getElementById('logTimeProject').textContent]")
        check(pre == [kanban["title"], "Habit Tracker"], f"from a card, its task comes preselected ({pre})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_logtime_tasks():
    asyncio.run(main())
