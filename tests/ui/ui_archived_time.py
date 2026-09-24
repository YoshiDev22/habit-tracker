import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def fmt_task_seconds():
    _, tl = call("GET", "/api/tasks", expect=200)
    return {t["id"]: t for t in tl["tasks"]}


async def main():
    token, col = seed()

    # 1. The new field agrees with the summary the list uses
    tasks = fmt_task_seconds()
    _, summary = call("GET", "/api/projects/summary", expect=200)
    from_summary = {}
    for p in summary["summaries"]:
        for tid, secs in (p.get("seconds_by_task") or {}).items():
            from_summary[int(tid)] = secs
    mismatches = [tid for tid, t in tasks.items() if t["seconds"] != from_summary.get(tid, 0)]
    check(not mismatches and sum(from_summary.values()) > 0,
          f"task.seconds matches the summary for every task ({len(tasks)} tasks, mismatches {mismatches})")

    # 2. Archive the project of a timed task: the task keeps its time
    timed = max(tasks.values(), key=lambda t: t["seconds"])
    _, projects = call("GET", "/api/projects", expect=200)
    project = next(p for p in projects["projects"] if p["id"] == timed["project_id"])
    check(not project.get("is_system"), f"timed task belongs to a normal project ({project['name']})")
    call("PATCH", f"/api/projects/{project['id']}", {"is_active": False}, expect=200)
    after = fmt_task_seconds()[timed["id"]]
    check(after["seconds"] == timed["seconds"], f"archived project: API keeps {timed['seconds']}s ({after['seconds']})")

    # 3. Board shows it
    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.5)
        shown = await b.js(f"""(() => {{
            const card = [...document.querySelectorAll('.board-card')].find(c => c.dataset.taskId === '{timed["id"]}');
            return card ? card.textContent : null;
        }})()""")
        h, m = divmod(timed["seconds"] // 60, 60)
        expected = f"{h}h {m}m" if h else f"{m}m"
        check(shown is not None and expected in shown, f"board card shows {expected} after archiving ({shown!r})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_archived_time():
    asyncio.run(main())
