"""Adjust a running stopwatch: add the time before ▶ was pressed; it keeps running."""
import asyncio
import datetime as dt
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE
from ui_two_tabs import Tab

TITLE = "Idea suelta sin proyecto"
results = []
SEEN = set()


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def new_sessions():
    _, tl = call("GET", "/api/tasks", expect=200)
    task = next(t for t in tl["tasks"] if t["title"] == TITLE)
    _, ss = call("GET", "/api/pomodoro", expect=200)
    fresh = [s for s in ss["sessions"] if s["task_id"] == task["id"] and s["id"] not in SEEN]
    SEEN.update(s["id"] for s in fresh)
    return fresh


ELAPSED = "Math.round(getElapsedMs(pomoState) / 60000)"   # minutes


def set_elapsed(h, m, sec):
    return (f"adjustHours.value = '{h}'; adjustMinutes.value = '{m}'; adjustSeconds.value = '{sec}';"
            "adjustSeconds.dispatchEvent(new Event('input'));")


async def main():
    token, _ = seed()
    task = next(t for t in call("GET", "/api/tasks", expect=200)[1]["tasks"] if t["title"] == TITLE)
    start = lambda mode: f"startTimerForTask({task['project_id']}, {task['id']}, '{mode}', {json.dumps(TITLE)})"
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
        new_sessions()

        # ✎ only for the stopwatch
        await js(start("focus"), wait=0.6)
        focus_btn = await js("!pomodoroBarAdjustBtn.classList.contains('hidden')")
        await js("stopTimer({ skipConfirm: true })", wait=0.8)
        await js(start("stopwatch"), wait=0.6)
        sw_btn = await js("!pomodoroBarAdjustBtn.classList.contains('hidden')")
        check(sw_btn and not focus_btn, f"✎ shows for the stopwatch only (stopwatch {sw_btn}, pomodoro {focus_btn})")

        # Type 0 h 45 min 0 s -> 45 min, keeps running
        await js("pomodoroBarAdjustBtn.click()", wait=0.4)
        opened = await js("!document.getElementById('adjustStartModal').classList.contains('hidden')")
        prefilled = await js("[adjustHours.value, adjustMinutes.value, adjustSeconds.value]")
        await js(set_elapsed(0, 45, 0), wait=0.2)
        preview = await js("document.getElementById('adjustStartPreview').textContent")
        expected_start = (dt.datetime.now() - dt.timedelta(minutes=45)).strftime("%H:%M")
        await js("document.getElementById('adjustStartApplyBtn').click()", wait=1.2)
        st = await js(f"({{status: pomoState.status, min: {ELAPSED}, ticking: pomoIntervalId !== null, clock: pomoClockText()}})")
        check(opened and prefilled[0] == "0" and prefilled[1] == "0" and int(prefilled[2]) < 5,
              f"opens with the time so far in h / min / s ({prefilled})")
        check(f"Empezaste a las {expected_start}" in preview, f"the start time is computed ({preview})")
        check(st["status"] == "running" and st["ticking"] and st["min"] == 45 and st["clock"].startswith("45:"),
              f"applied: 45 min and still running ({st})")

        # Cancel leaves it alone
        await js("pomodoroBarAdjustBtn.click()", wait=0.3)
        await js(set_elapsed(3, 0, 0) + " document.getElementById('adjustStartCancelBtn').click()", wait=0.4)
        check(await js(ELAPSED) == 45, "cancel changes nothing")

        # Exactly 2 h 0 min 30 s
        await js("pomodoroBarAdjustBtn.click()", wait=0.3)
        await js(set_elapsed(2, 0, 30), wait=0.2)
        await js("document.getElementById('adjustStartApplyBtn').click()", wait=0.5)
        secs = await js("Math.floor(getElapsedMs(pomoState) / 1000)")
        m = secs // 60
        check(7230 <= secs <= 7232, f"exact h/min/s: 2:00:30 ({secs} s)")

        # Stopping saves the adjusted time, with the adjusted start
        await js("stopTimer()", wait=2.0)
        saved = new_sessions()
        started = dt.datetime.fromisoformat(saved[0]["started_at"]) if saved else None
        check(len(saved) == 1 and 119 * 60 <= saved[0]["duration_seconds"] <= 121 * 60,
              f"saves the adjusted time ({[s['duration_seconds'] for s in saved]})")
        check(started is not None and dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - started > dt.timedelta(minutes=118),
              f"with the adjusted start ({saved and saved[0]['started_at']})")

        # Can't go past 8 h; reaching it stops and asks (the way to test the cap)
        await js(start("stopwatch"), wait=0.6)
        await js("pomodoroBarAdjustBtn.click()", wait=0.3)
        await js(set_elapsed(9, 0, 0), wait=0.2)
        bad = await js("[!document.getElementById('adjustStartError').classList.contains('hidden'), document.getElementById('adjustStartPreview').textContent]")
        await js("document.getElementById('adjustStartApplyBtn').click()", wait=0.3)
        still_open = await js("!document.getElementById('adjustStartModal').classList.contains('hidden')")
        check(bad[0] and bad[1] == "" and still_open, f"more than 8 h is refused ({bad}, open={still_open})")
        await js(set_elapsed(8, 0, 0), wait=0.2)
        preview = await js("document.getElementById('adjustStartPreview').textContent")
        await js("document.getElementById('adjustStartApplyBtn').click()", wait=1.5)
        st = await js("({ask: !document.getElementById('idleCheckModal').classList.contains('hidden'), clock: pomoClockText()})")
        check("tope de 8 h" in preview, f"8 h is the cap ({preview})")
        check(st == {"ask": True, "clock": "8:00:00"}, f"at 8 h it stops and asks how long you worked ({st})")
        await js("document.getElementById('idleCheckHours').value = '1'; document.getElementById('idleCheckMinutes').value = '30'; document.getElementById('idleCheckSaveBtn').click()", wait=2.0)
        saved = new_sessions()
        check(len(saved) == 1 and saved[0]["duration_seconds"] == 90 * 60, f"then saves what you say ({[s['duration_seconds'] for s in saved]})")

        # Two tabs: adjust in one, stop from the other -> the adjusted time is saved once
        await js(start("stopwatch"), wait=0.6)
        tab2 = await Tab.open(b, BASE + "/")
        await asyncio.sleep(3.0)
        await js("pomodoroBarAdjustBtn.click()", wait=0.3)
        await js(set_elapsed(0, 30, 0) + " document.getElementById('adjustStartApplyBtn').click()", wait=1.0)
        m2 = await tab2.js(ELAPSED)
        check(m2 == 30, f"the other tab follows the adjustment ({m2} min)")
        await tab2.js("stopTimer()")
        await asyncio.sleep(2.0)
        st1 = await js("pomoState.status")
        saved = new_sessions()
        check(len(saved) == 1 and 29 * 60 <= saved[0]["duration_seconds"] <= 31 * 60 and st1 == "idle",
              f"stopping from the other tab saves the adjusted 30 min once; this tab goes idle ({[s['duration_seconds'] for s in saved]}, {st1})")
        await tab2.ws.close()

        # Change the task too: all the time since it started goes to the new one
        _, tl = call("GET", "/api/tasks", expect=200)
        kanban = next(t for t in tl["tasks"] if t["title"].startswith("Revisión de idea"))
        def sessions_of(task_id):
            _, ss = call("GET", f"/api/pomodoro?task_id={task_id}", expect=200)
            return ss["sessions"]
        before_k = len(sessions_of(kanban["id"]))
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        await js(start("stopwatch"), wait=0.6)
        await js("pomodoroBarAdjustBtn.click()", wait=1.0)
        opts = await js("[...document.getElementById('adjustStartTask').options].map(o => o.textContent)")
        groups = await js("[...document.querySelectorAll('#adjustStartTask optgroup')].map(g => g.label)")
        await js(f"document.getElementById('adjustStartTask').value = '{kanban['id']}';" + set_elapsed(0, 30, 0)
                 + "document.getElementById('adjustStartApplyBtn').click()", wait=1.0)
        st = await js("({task: pomoState.taskId, project: pomoState.projectId, label: pomodoroBarLabel.textContent, "
                      "timing: [...document.querySelectorAll('.board-card.timing .board-card-title')].map(e => e.textContent)})")
        check(opts[0] == TITLE and "Habit Tracker" in groups and any(o.startswith("Revisión de idea") for o in opts),
              f"the task list starts with the current one, grouped by project ({opts[:3]}, {groups})")
        check(st["task"] == kanban["id"] and st["project"] == kanban["project_id"] and "Revisión de idea" in st["label"]
              and st["timing"] == [kanban["title"]], f"the running stopwatch moves to the new task ({st})")
        await js("stopTimer()", wait=2.0)
        moved = sessions_of(kanban["id"])
        check(len(moved) == before_k + 1 and 29 * 60 <= moved[0]["duration_seconds"] <= 31 * 60 and not new_sessions(),
              f"the 30 min are saved on the new task only ({[s['duration_seconds'] for s in moved[:1]]})")

        await js(start("stopwatch"), wait=0.6)
        await js("pomodoroBarAdjustBtn.click()", wait=1.0)
        await js(set_elapsed(1, 25, 0), wait=0.2)
        await b.shot("adjust_start", full=False)
        await js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))", wait=0.3)
        check(await js("document.getElementById('adjustStartModal').classList.contains('hidden')"), "Escape closes it")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_adjust():
    asyncio.run(main())
