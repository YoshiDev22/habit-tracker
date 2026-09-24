"""Does the running time survive closing the browser, logging out, and a
network failure? Uses one Edge profile across restarts, like a real user."""
import asyncio
import json
import sys

import api
from api import call, login
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Idea suelta'))"
TITLE = "Idea suelta sin proyecto"


def sessions_for(title):
    _, tl = call("GET", "/api/tasks", expect=200)
    task = next(t for t in tl["tasks"] if t["title"] == title)
    _, ss = call("GET", "/api/pomodoro", expect=200)
    return [s for s in ss["sessions"] if s["task_id"] == task["id"]]


async def open_app(b, first=False, token=None):
    await b.viewport(1280, 900)
    if first:
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
    await b.goto(BASE + "/", wait=3.0)
    await b.js(CLOSE_WELCOME)
    await b.js("document.getElementById('tabProjects').click()")
    await asyncio.sleep(1.2)


async def main():
    token, col = seed()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    state = "({status: pomoState.status, mode: pomoState.mode, task: pomoState.taskTitle, elapsed: Math.round(getElapsedMs(pomoState) / 1000), bar: !pomodoroBar.classList.contains('hidden'), cardTiming: !!(" + CARD + " || {classList: {contains: () => false}}).classList.contains('timing')})"

    # 1. Close the window with the stopwatch running, come back later
    b = Browser(fresh=True)
    await b.start()
    await open_app(b, first=True, token=token)
    await b.js(f"{CARD}.querySelector('.board-card-play').click()")
    await asyncio.sleep(1.5)
    # Pretend it has been running for 5 minutes
    await b.js("pomoState.startedEpochMs = Date.now() - 300000; savePomoState();")
    await asyncio.sleep(0.5)
    await b.quit()
    await asyncio.sleep(3)

    b = Browser(fresh=False)
    await b.start()
    await open_app(b)
    st = await b.js(state)
    check(st["status"] == "running" and st["mode"] == "stopwatch" and st["task"] == TITLE and 303 <= st["elapsed"] <= 330
          and st["bar"] and st["cardTiming"],
          f"closing the window keeps the stopwatch running; it resumes counting on return ({st})")
    await b.shot("persist_resumed", full=False)

    # 2. Log out with it running: the time is saved before the token goes
    await b.js("document.getElementById('logoutBtn').click()")
    await asyncio.sleep(2.5)
    saved = sessions_for(TITLE)
    check(len(saved) == 1 and 300 <= saved[0]["duration_seconds"] <= 340 and saved[0]["project_id"] is not None,
          f"logging out saves the running time ({[s['duration_seconds'] for s in saved]} s)")
    check(await b.js("localStorage.getItem('pomodoro_state')") is None, "and clears the timer state")

    # 3. A pomodoro that ends while the window is closed is saved on return
    await b.js(f"localStorage.setItem('access_token', {json.dumps(api.TOKEN)});")
    await open_app(b)
    await b.js(f"{CARD}.click()")
    await asyncio.sleep(1.0)
    await b.js("document.querySelector('#cardTimer [data-timer=focus]').click()")
    await asyncio.sleep(1.0)
    # 10 s of margin: closing the browser takes a few seconds, and if the pomodoro
    # ends before it dies the save races the localStorage flush (see BACKLOG).
    await b.js("pomoState.startedEpochMs = Date.now() - 1500000 + 10000; pomoState.targetEpochMs = Date.now() + 10000; savePomoState();")
    await asyncio.sleep(0.5)
    import time as _t
    _q = _t.time()
    await b.quit()
    print(f"DEBUG quit took {_t.time() - _q:.1f}s, killed={b.proc.returncode}")
    await asyncio.sleep(13)  # it ends while the browser is closed

    b = Browser(fresh=False)
    await b.start()
    await open_app(b)
    saved = sessions_for(TITLE)
    check(len(saved) == 2 and any(s["duration_seconds"] == 1500 for s in saved),
          f"a pomodoro that ended while closed is saved as 25 min on return ({[s['duration_seconds'] for s in saved]})")
    check(await b.js("pomoState.status") == "idle", "and the timer is idle again")

    # 4. Network down when stopping: queued, sent on the next visit
    await b.js(f"{CARD}.querySelector('.board-card-play').click()")
    await asyncio.sleep(1.2)
    await b.js("pomoState.startedEpochMs = Date.now() - 120000; savePomoState();")
    await b.send("Network.enable")
    await b.send("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=-1, uploadThroughput=-1)
    await b.js(f"{CARD}.querySelector('.board-card-play').click()")
    await asyncio.sleep(2.0)
    pending = await b.js("JSON.parse(localStorage.getItem('pomodoro_pending') || '[]').length")
    check(pending == 1 and len(sessions_for(TITLE)) == 2, f"offline stop keeps the time in the pending queue ({pending} queued, {len(sessions_for(TITLE))} saved)")
    await b.send("Network.emulateNetworkConditions", offline=False, latency=0, downloadThroughput=-1, uploadThroughput=-1)
    await b.quit()
    await asyncio.sleep(2)

    b = Browser(fresh=False)
    await b.start()
    await open_app(b)
    await asyncio.sleep(1.5)
    saved = sessions_for(TITLE)
    pending = await b.js("JSON.parse(localStorage.getItem('pomodoro_pending') || '[]').length")
    check(len(saved) == 3 and any(115 <= s["duration_seconds"] <= 130 for s in saved) and pending == 0,
          f"the queued time is sent on the next visit ({[s['duration_seconds'] for s in saved]}, {pending} left)")
    await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith("[exception]")]
    print("exceptions:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_persist():
    asyncio.run(main())
