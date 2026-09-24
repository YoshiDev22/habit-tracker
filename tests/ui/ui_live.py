import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

KANBAN_CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Revisión de idea'))"


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def js(expr, wait=0.8):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    card_state = f"""(() => {{ const c = {KANBAN_CARD}; const t = c.querySelector('.board-card-time'); const p = c.querySelector('.board-card-play');
        const vis = el => getComputedStyle(el).display !== 'none';
        return {{timing: c.classList.contains('timing'), shown: [...t.children].filter(vis).map(e => e.textContent),
                 icon: [...p.children].filter(vis).map(e => e.textContent).join(''), label: p.getAttribute('aria-label')}}; }})()"""

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view'); localStorage.removeItem('board_selected');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)

        st = await b.js(card_state)
        check(st["timing"] is False and st["shown"] == ["0m"] and st["icon"] == "▶", f"idle card shows its total and ▶ ({st})")

        await js(f"{KANBAN_CARD}.querySelector('.board-card-play').click()", wait=2.2)
        st = await b.js(card_state)
        check(st["timing"] and st["shown"][0] in ("00:01", "00:02", "00:03") and st["icon"] == "■" and st["label"] == "Detener y guardar el tiempo",
              f"running card shows the live clock and ■ ({st})")
        await asyncio.sleep(1.2)
        later = (await b.js(card_state))["shown"][0]
        check(later != st["shown"][0], f"the clock on the card keeps moving ({st['shown'][0]} -> {later})")
        await b.shot("live_card", full=False)

        # The same button stops (no restart prompt, no loop)
        await js("pomoState.startedEpochMs = Date.now() - 90000; savePomoState();", wait=0.3)
        await js(f"{KANBAN_CARD}.querySelector('.board-card-play').click()", wait=1.8)
        confirm_open = await b.js("!document.getElementById('confirmModal').classList.contains('hidden')")
        st = await b.js(card_state)
        _, ss = call("GET", "/api/pomodoro", expect=200)
        saved = [s for s in ss["sessions"] if s["duration_seconds"] >= 89 and s["duration_seconds"] <= 95]
        check(not confirm_open and await b.js("pomoState.status") == "idle" and st["icon"] == "▶" and len(saved) == 1,
              f"clicking ■ stops and saves the time, no restart prompt ({st}, saved={len(saved)})")
        check(st["shown"] == ["1m"], f"card shows the new total after stopping ({st['shown']})")

        # Card detail: direct buttons, Detener with live time while running
        await js(f"{KANBAN_CARD}.click()", wait=1.0)
        vis = "[...document.querySelectorAll('#cardTimer button')].filter(b => getComputedStyle(b).display !== 'none').map(b => b.textContent.trim())"
        idle = await b.js(vis)
        check(idle == ["▶ Cronómetro", "🍅 Pomodoro", "✍️ Registrar a mano"], f"detail shows direct buttons ({idle})")
        await js("document.querySelector('#cardTimer [data-timer=\"stopwatch\"]').click()", wait=1.5)
        check(await b.js("!document.getElementById('cardModal').classList.contains('hidden') && pomoState.status === 'running'"),
              "▶ Cronómetro starts at once and the detail stays open")
        await js("(() => { const n = document.getElementById('cardNotes'); n.focus(); n.value = 'Escrito mientras corre'; n.blur(); })()", wait=1.2)
        _, tl = call("GET", "/api/tasks", expect=200)
        k = next(t for t in tl["tasks"] if t["title"].startswith("Revisión de idea"))
        check(k["notes"] == "Escrito mientras corre" and await b.js("pomoState.status") == "running",
              "you can keep editing the task while it runs")
        await asyncio.sleep(0.5)
        running = await b.js(vis)
        check(len(running) == 2 and running[0].startswith("■ Detener 00:0") and running[1] == "✍️ Registrar a mano",
              f"while running, the detail offers ■ Detener with the live time ({running})")
        await b.shot("live_detail", full=False)
        await js("pomoState.startedEpochMs = Date.now() - 5000; savePomoState(); document.querySelector('#cardTimer [data-timer=\"stop\"]').click()", wait=1.0)
        check(await b.js("pomoState.status === 'idle' && !document.getElementById('cardModal').classList.contains('hidden')"),
              "Detener stops it and the detail stays open")
        back = await b.js(vis)
        check(back == ["▶ Cronómetro", "🍅 Pomodoro", "✍️ Registrar a mano"], f"buttons return to idle ({back})")

        # Registrar a mano opens the manual form directly
        await js("document.querySelector('#cardTimer [data-timer=\"manual\"]').click()", wait=1.5)
        m = await b.js("({card: document.getElementById('cardModal').classList.contains('hidden'), log: !document.getElementById('logTimeModal').classList.contains('hidden'), task: document.getElementById('logTimeTask').selectedOptions[0].textContent})")
        check(m == {"card": False, "log": True, "task": "Revisión de idea para cambiar a kanban"}, f"'Registrar a mano' opens the form at once ({m})")
        await js("document.getElementById('closeLogTimeBtn').click()", wait=0.4)

        # List view: same behaviour on the row
        await js("document.querySelector('[data-projects-view=\"list\"]').click()", wait=0.6)
        await js("[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent === 'Habit Tracker').querySelector('.project-toggle').click()", wait=1.5)
        row = "[...document.querySelectorAll('.task-row')].find(r => r.innerText.includes('Revisión de idea'))"
        await js(f"{row}.querySelector('.task-play').click()", wait=2.2)
        r = await b.js(f"(() => {{ const r = {row}; const vis = el => getComputedStyle(el).display !== 'none'; return {{timing: r.classList.contains('timing'), time: [...r.querySelector('.task-time').children].filter(vis).map(e => e.textContent), icon: [...r.querySelector('.task-play').children].filter(vis).map(e => e.textContent).join('')}}; }})()")
        check(r["timing"] and r["time"][0].startswith("00:0") and r["icon"] == "■", f"list row shows the live clock and ■ ({r})")
        await js("pomoState.startedEpochMs = Date.now() - 5000; savePomoState();", wait=0.2)
        await js(f"{row}.querySelector('.task-play').click()", wait=1.2)
        check(await b.js("pomoState.status") == "idle", "■ on the list row stops too")
        await js("document.querySelector('[data-projects-view=\"board\"]').click()", wait=0.4)

        # Organizar: clear column badges and the "done" checkbox
        await js("document.getElementById('boardConfigBtn').click()", wait=1.5)
        badges = await b.js("[...document.querySelectorAll('#configColumns .config-row')].map(r => r.querySelector('.config-name').value + ':' + r.querySelector('.config-type').textContent)")
        check(badges == ["Por hacer:📥 Entrada", "Haciendo:", "Hecho:✓ Terminada"], f"columns show Entrada / nothing / Terminada ({badges})")
        await js("(() => { const f = document.getElementById('configColumnForm'); f.querySelector('input[type=text]').value = 'Entregado'; document.getElementById('configColumnDone').checked = true; f.requestSubmit(); })()", wait=1.5)
        _, bl = call("GET", "/api/boards", expect=200)
        cats = {c["name"]: c["category"] for c in bl["boards"][0]["columns"]}
        check(cats.get("Entregado") == "done", f"the checkbox makes a 'done' column ({cats})")
        check(not await b.js("document.getElementById('configColumnDone').checked"), "the checkbox resets after adding")
        # Empty "Haciendo" first: the seed left the kanban card there
        _, tl = call("GET", "/api/tasks", expect=200)
        for t in tl["tasks"]:
            if t["column_id"] == col["Haciendo"]:
                call("PATCH", f"/api/tasks/{t['id']}", {"column_id": col["Por hacer"]}, expect=200)
        await b.js("[...document.querySelectorAll('#configColumns .config-row')].find(r => r.querySelector('.config-name').value === 'Haciendo').querySelector('.config-delete-column').click()")
        await asyncio.sleep(1.2)
        _, bl = call("GET", "/api/boards", expect=200)
        names = [c["name"] for c in bl["boards"][0]["columns"]]
        check("Haciendo" not in names, f"the last 'in progress' column can be deleted when empty ({names})")
        await b.shot("config_columns_new", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_live():
    asyncio.run(main())
