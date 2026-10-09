"""The stopwatch never interrupts; at the 8 h cap it stops and the user says how long they worked."""
import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

TITLE = "Idea suelta sin proyecto"
AUTO_NOTE = "Cerrado automáticamente a las 8 h"
results = []
H = 3600 * 1000
SEEN = set()


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def sessions_for(title):
    _, tl = call("GET", "/api/tasks", expect=200)
    task = next(t for t in tl["tasks"] if t["title"] == title)
    _, ss = call("GET", "/api/pomodoro", expect=200)
    return [s for s in ss["sessions"] if s["task_id"] == task["id"]]


def new_session(title):
    fresh = [s for s in sessions_for(title) if s["id"] not in SEEN]
    SEEN.update(s["id"] for s in fresh)
    return fresh


STATE = """({status: pomoState.status, ask: !document.getElementById('idleCheckModal').classList.contains('hidden'),
    msg: document.getElementById('idleCheckMessage').textContent,
    h: document.getElementById('idleCheckHours').value, m: document.getElementById('idleCheckMinutes').value,
    hint: !document.getElementById('idleCheckHint').classList.contains('hidden'),
    last: document.getElementById('idleCheckLast').textContent,
    err: !document.getElementById('idleCheckError').classList.contains('hidden'),
    clock: pomoClockText(), ticking: pomoIntervalId !== null})"""


async def main():
    token, _ = seed()
    task = next(t for t in call("GET", "/api/tasks", expect=200)[1]["tasks"] if t["title"] == TITLE)
    start_js = f"startTimerForTask({task['project_id']}, {task['id']}, 'stopwatch', {json.dumps(TITLE)})"

    def rig(started_ago_ms, active_ago_ms):
        return (f"pomoState.startedEpochMs = Date.now() - {started_ago_ms}; savePomoState();"
                f"localStorage.setItem('pomodoro_activity', String(Date.now() - {active_ago_ms}));")

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
        new_session(TITLE)

        # 1. Idle for 2h30 but only 3h running: no interruption
        await js(start_js, wait=0.5)
        await js(rig(3 * H, 2.5 * H), wait=1.5)
        s = await js(STATE)
        check(s["status"] == "running" and not s["ask"], f"before the cap it never asks, even idle ({s['status']}, ask={s['ask']})")
        await js("lastActivityWrite = 0; document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}))", wait=0.2)
        recent = await js("Date.now() - Number(localStorage.getItem('pomodoro_activity')) < 5000")
        check(recent, "a click records activity")
        await js("stopTimer()", wait=2.0)
        new_session(TITLE)

        # 2. Reaching the cap live: stops at 8:00:00 and asks, prefilled with 8 h
        await js(start_js, wait=0.5)
        await js(rig(8 * H - 2000, 3 * H), wait=4.0)
        s = await js(STATE)
        check(s["ask"] and not s["ticking"] and s["clock"] == "8:00:00" and (s["h"], s["m"]) == ("8", "0")
              and "¿Cuánto trabajaste en «Idea suelta sin proyecto»?" in s["msg"],
              f"at the cap: stops at 8 h and asks, prefilled 8 h ({s['clock']}, {s['h']}h{s['m']}, {s['msg']})")
        check(s["hint"] and ("(4h 59m)" in s["last"] or "(5h 0m)" in s["last"]), f"the last activity is a hint ({s['last']})")
        await js("document.getElementById('idleCheckUseLast').click()", wait=0.2)
        s = await js(STATE)
        check((s["h"], s["m"]) in (("4", "59"), ("5", "0")), f"'Usar esa hora' fills it in ({s['h']}h {s['m']}m)")
        # The user decides: 3 h
        await js("document.getElementById('idleCheckHours').value = '3'; document.getElementById('idleCheckMinutes').value = '0';"
                 "document.getElementById('idleCheckSaveBtn').click()", wait=2.5)
        saved = new_session(TITLE)
        check(len(saved) == 1 and saved[0]["duration_seconds"] == 3 * 3600 and not saved[0]["note"],
              f"saves what the user says, no auto note ({[(x['duration_seconds'], x['note']) for x in saved]})")

        # 3. The overnight case: on return it asks; the hint gives the 35 min
        await js(start_js, wait=0.5)
        await js(rig(9 * H, 9 * H - 35 * 60 * 1000), wait=0.2)
        await b.goto(BASE + "/", wait=1.0)
        # Esperar a que la pregunta salga (con la máquina ocupada, 3 s fijos a veces no alcanzaban)
        await b.wait_for("!document.getElementById('idleCheckModal').classList.contains('hidden') && document.getElementById('idleCheckLast').textContent.includes('35m')", timeout=15)
        s = await js(STATE)
        check(s["status"] == "running" and s["ask"] and s["clock"] == "8:00:00" and "(35m)" in s["last"],
              f"overnight: on return it asks, clock held at 8 h ({s['last']}, {s['clock']})")
        # More than 8 h is refused
        await js("document.getElementById('idleCheckHours').value = '9'; document.getElementById('idleCheckSaveBtn').click()", wait=0.5)
        s = await js(STATE)
        check(s["ask"] and not new_session(TITLE), "more than 8 h is refused (the browser blocks it; nothing saved)")
        await js("document.getElementById('idleCheckUseLast').click(); document.getElementById('idleCheckSaveBtn').click()", wait=2.5)
        saved = new_session(TITLE)
        check(len(saved) == 1 and 34 * 60 <= saved[0]["duration_seconds"] <= 36 * 60 and not saved[0]["note"],
              f"saved the 35 min ({[(x['duration_seconds'], x['note']) for x in saved]})")

        # 4. Active near the cap: also asks (the user decides); no hint; keeping 8 h saves 8 h, no note
        await js(start_js, wait=0.5)
        await js(rig(9 * H, 60 * 1000), wait=0.2)
        await b.goto(BASE + "/", wait=1.0)
        await b.wait_for("!document.getElementById('idleCheckModal').classList.contains('hidden')", timeout=15)
        s = await js(STATE)
        check(s["ask"] and not s["hint"], f"active at the cap: asks, without the hint (hint={s['hint']})")
        await js("document.getElementById('idleCheckSaveBtn').click()", wait=2.5)
        saved = new_session(TITLE)
        check(len(saved) == 1 and saved[0]["duration_seconds"] == 8 * 3600 and not saved[0]["note"],
              f"keeping 8 h saves 8 h without the auto note ({[(x['duration_seconds'], x['note']) for x in saved]})")
        await b.shot("cap_ask", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_idle():
    asyncio.run(main())
