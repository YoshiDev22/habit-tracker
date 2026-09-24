"""Two tabs of the app in one browser must not save the same time twice."""
import asyncio
import itertools
import json
import sys
import urllib.request

import websockets

import api
from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

TITLE = "Idea suelta sin proyecto"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def sessions_for(title):
    _, tl = call("GET", "/api/tasks", expect=200)
    task = next(t for t in tl["tasks"] if t["title"] == title)
    _, ss = call("GET", "/api/pomodoro", expect=200)
    return [s for s in ss["sessions"] if s["task_id"] == task["id"]]


class Tab:
    """A second page of the same browser, driven over its own CDP socket."""
    def __init__(self, ws):
        self.ws = ws
        self.ids = itertools.count(1000)

    @classmethod
    async def open(cls, b, url):
        created = await b.send("Target.createTarget", url=url)
        tid = created["targetId"]
        for _ in range(50):
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{b.port}/json").read())
            t = next((t for t in targets if t["id"] == tid), None)
            if t and t.get("webSocketDebuggerUrl"):
                break
            await asyncio.sleep(0.2)
        ws = await websockets.connect(t["webSocketDebuggerUrl"], max_size=50_000_000)
        tab = cls(ws)
        await tab.send("Emulation.setFocusEmulationEnabled", enabled=True)
        return tab

    async def send(self, method, **params):
        i = next(self.ids)
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == i:
                return msg.get("result", {})

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")


async def main():
    token, _ = seed()
    b = Browser(fresh=True)
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.2)
        task = next(t for t in call("GET", "/api/tasks", expect=200)[1]["tasks"] if t["title"] == TITLE)
        base_n = len(sessions_for(TITLE))

        # 1. A pomodoro ends with two tabs open: saved once
        await b.js(f"startTimerForTask({task['project_id']}, {task['id']}, 'focus', {json.dumps(TITLE)})")
        await asyncio.sleep(0.5)
        await b.js("pomoState.startedEpochMs = Date.now() - 1500000 + 6000; pomoState.targetEpochMs = Date.now() + 6000; savePomoState(); scheduleEndBeep(6000);")
        tab2 = await Tab.open(b, BASE + "/")
        await asyncio.sleep(3.0)
        running2 = await tab2.js("pomoState.status")
        await asyncio.sleep(6.0)
        s1 = sessions_for(TITLE)
        idle = [await b.js("pomoState.status"), await tab2.js("pomoState.status")]
        check(running2 == "running", f"the second tab picked up the running pomodoro ({running2})")
        check(len(s1) == base_n + 1 and s1[0]["duration_seconds"] == 1500 and idle == ["idle", "idle"],
              f"a pomodoro ending in two tabs is saved once ({[s['duration_seconds'] for s in s1]}, {idle})")

        # 2. Stopwatch stopped in tab 1, then in tab 2 (stale copy): saved once, tab 2 says so
        await b.js(f"startTimerForTask({task['project_id']}, {task['id']}, 'stopwatch', {json.dumps(TITLE)})")
        await asyncio.sleep(0.5)
        await b.js("pomoState.startedEpochMs = Date.now() - 180000; savePomoState();")
        await tab2.send("Page.reload")
        await asyncio.sleep(3.0)
        st2 = await tab2.js("[pomoState.status, pomoState.mode]")
        await b.js("stopTimer()")
        await asyncio.sleep(2.0)
        await tab2.js("stopTimer()")
        await asyncio.sleep(2.0)
        msg2 = await tab2.js("[pomoState.status, pomodoroBar.classList.contains('hidden')]")
        s2 = sessions_for(TITLE)
        check(st2 == ["running", "focus"] or st2[0] == "running", f"tab 2 had the stopwatch running ({st2})")
        check(len(s2) == len(s1) + 1, f"stopping in both tabs saves once ({len(s2) - len(s1)} new)")
        check(msg2 == ["idle", True], f"the second tab stops by itself when the first saves ({msg2})")

        # 3. A queued session is sent once on reload, even with two tabs starting together
        payload = {"project_id": task["project_id"], "task_id": task["id"], "session_date": s2[0]["session_date"],
                   "started_at": "2026-09-23T03:00:00", "ended_at": "2026-09-23T03:02:00", "duration_seconds": 120,
                   "planned_seconds": 120, "mode": "focus", "was_completed": True, "source": "stopwatch"}
        await b.js(f"localStorage.setItem('pomodoro_pending', JSON.stringify([{json.dumps(payload)}]))")
        await tab2.send("Page.reload")
        await b.goto(BASE + "/", wait=4.0)
        s3 = sessions_for(TITLE)
        left = await b.js("localStorage.getItem('pomodoro_pending')")
        check(len(s3) == len(s2) + 1 and left is None, f"a queued session is sent once ({len(s3) - len(s2)} new, queue {left})")

        # 4. Something queued while a flush is sending is kept
        await b.js(f"""(async () => {{
            localStorage.setItem('pomodoro_pending', JSON.stringify([{json.dumps({**payload, 'duration_seconds': 60, 'ended_at': '2026-09-23T03:01:00'})}]));
            // queue a new one while the first POST is on the wire
            const original = apiFetch;
            apiFetch = async (...args) => {{
                apiFetch = original;
                queuePendingSession({json.dumps({**payload, 'duration_seconds': 90, 'ended_at': '2026-09-23T03:01:30'})});
                return original(...args);
            }};
            await flushPendingSessions();
        }})()""")
        await asyncio.sleep(1.0)
        left = await b.js("JSON.parse(localStorage.getItem('pomodoro_pending') || '[]').map(p => p.duration_seconds)")
        s4 = sessions_for(TITLE)
        check(left == [90] and len(s4) == len(s3) + 1, f"what is queued during a flush stays queued ({left}, {len(s4) - len(s3)} sent)")
        await tab2.ws.close()
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith("[exception]")]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")



def test_two_tabs():
    asyncio.run(main())
