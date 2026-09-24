"""Card detail: time refresh after stopping, time history, remembered tab."""
import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

STAGE = 99   # every stage; lower it to run only the first ones while debugging
KANBAN_CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Revisión de idea'))"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def minutes(text):
    t = text.strip()
    h = int(t.split("h")[0]) if "h" in t else 0
    m = int(t.split("h")[-1].replace("m", "").strip() or 0)
    return h * 60 + m


async def main():
    token, col = seed()
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

        # --- 1. Stopping from the open card updates its time
        await js(f"{KANBAN_CARD}.click()", wait=1.2)
        before = await js("document.getElementById('cardTime').textContent")
        await js("document.querySelector('#cardTimer [data-timer=stopwatch]').click()", wait=0.8)
        await js("pomoState.startedEpochMs = Date.now() - 5 * 60000; savePomoState();", wait=0.3)
        await js("document.querySelector('#cardTimer [data-timer=stop]').click()", wait=2.0)
        st = await js("({open: !document.getElementById('cardModal').classList.contains('hidden'), time: document.getElementById('cardTime').textContent})")
        check(st["open"] and minutes(st["time"]) - minutes(before) == 5,
              f"stopping from the open card updates its time without closing ({before} -> {st['time']})")
        card_time = await js(f"{KANBAN_CARD}.querySelector('.board-card-time, .card-time-badge, [class*=time]').textContent")
        check(st["time"] in card_time, f"the board card behind shows the same ({card_time})")

        if STAGE >= 2:
            HIST = """({open: !document.getElementById('cardModal').classList.contains('hidden'),
                logOpen: !document.getElementById('logTimeModal').classList.contains('hidden'),
                time: document.getElementById('cardTime').textContent,
                meta: document.getElementById('cardHistoryMeta').textContent,
                rows: [...document.querySelectorAll('#cardHistory .session-row')].map(r =>
                    [r.querySelector('.session-origin').textContent, r.querySelector('.session-when').textContent])})"""
            _, tl = call("GET", "/api/tasks", expect=200)
            kanban = next(t for t in tl["tasks"] if t["title"].startswith("Revisión de idea"))
            _, ss = call("GET", f"/api/pomodoro?task_id={kanban['id']}", expect=200)
            api_rows = [s for s in ss["sessions"] if s["mode"] == "focus"]
            h = await js(HIST)
            check(len(h["rows"]) == min(5, len(api_rows)) and all(s["task_id"] == kanban["id"] for s in ss["sessions"]),
                  f"history lists the task's sessions ({len(h['rows'])} rows, API {len(api_rows)})")
            check(h["rows"][0][0] == "▶" and h["rows"][0][1].endswith("· 5m"), f"the stopped stopwatch is on top ({h['rows'][0]})")
            total_api = sum(s["duration_seconds"] for s in api_rows) // 60
            check(minutes(h["time"]) == total_api, f"history adds up to the card time ({total_api} min / {h['time']})")

            # Manual entry from the card: opens on top, card stays open
            await js("document.querySelector('#cardTimer [data-timer=manual]').click()", wait=1.2)
            h = await js(HIST)
            check(h["open"] and h["logOpen"], "✍️ opens the log above the card without closing it")
            top = await js("document.elementFromPoint(640, 450).closest('.modal').id")
            check(top == "logTimeModal", f"the log window is on top ({top})")
            await js("logTimeHoursEl.value = ''; logTimeMinutesEl.value = '20'; logTimeMinutesEl.dispatchEvent(new Event('input')); logTimeNoteEl.value = 'Leí docs';", wait=0.3)
            await js("logTimeSubmitBtn.click()", wait=2.5)
            h = await js(HIST)
            check(h["open"] and not h["logOpen"] and minutes(h["time"]) == total_api + 20,
                  f"after saving: back on the card, time +20m ({h['time']})")
            man = [r for r in h["rows"] if r[0] == "✍️"]
            check(len(man) == 1 and man[0][1].endswith("· 20m") and len(h["rows"]) == 2, f"new manual row in the history ({h['rows']})")
            note = await js("[...document.querySelectorAll('#cardHistory .session-row')].find(r => r.querySelector('.session-origin').textContent === '✍️').querySelector('.session-detail').textContent")
            check(note == "Registrado a mano — Leí docs", f"row explains its origin and note ({note})")

            # Edit it to 30m
            await js("[...document.querySelectorAll('#cardHistory .session-row')].find(r => r.querySelector('.session-origin').textContent === '✍️').querySelector('[data-action=edit]').click()", wait=1.2)
            title = await js("logTimeTitleEl.textContent")
            await js("logTimeHoursEl.value = ''; logTimeMinutesEl.value = '30'; logTimeMinutesEl.dispatchEvent(new Event('input'));", wait=0.3)
            await js("logTimeSubmitBtn.click()", wait=2.5)
            h = await js(HIST)
            man = [r for r in h["rows"] if r[0] == "✍️"]
            check(title == "Editar registro" and minutes(h["time"]) == total_api + 30 and man[0][1].endswith("· 30m"),
                  f"✎ edits the entry ({title}, {h['time']}, {man})")

            # Escape with the log open closes only the log
            await js("document.querySelector('#cardHistory .session-row [data-action=edit]').click()", wait=1.0)
            await js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))", wait=0.5)
            h = await js(HIST)
            check(h["open"] and not h["logOpen"], "Escape closes the log, not the card")

            # Delete asks first; cancel keeps it, confirm removes it
            n_before = len(h["rows"])
            await js("[...document.querySelectorAll('#cardHistory .session-row')].find(r => r.querySelector('.session-origin').textContent === '✍️').querySelector('[data-action=delete]').click()", wait=0.6)
            await js("document.getElementById('confirmModalCancelBtn').click()", wait=0.8)
            h = await js(HIST)
            check(len(h["rows"]) == n_before and minutes(h["time"]) == total_api + 30, "cancelling the delete keeps the entry")
            await js("[...document.querySelectorAll('#cardHistory .session-row')].find(r => r.querySelector('.session-origin').textContent === '✍️').querySelector('[data-action=delete]').click()", wait=0.6)
            await js("document.getElementById('confirmModalConfirmBtn').click()", wait=2.5)
            h = await js(HIST)
            check(h["open"] and minutes(h["time"]) == total_api and [r[0] for r in h["rows"]] == ["▶"],
                  f"confirming removes it and the time goes back ({h['time']})")
            _, other = call("GET", f"/api/pomodoro?task_id={kanban['id']}", expect=200)
            await b.shot("card_history", full=False)

            # another user asking for my task's sessions gets nothing
            import api as api_mod
            mine = api_mod.TOKEN
            from api import login
            login("otro@test.com")
            _, foreign = call("GET", f"/api/pomodoro?task_id={kanban['id']}", expect=200)
            api_mod.TOKEN = mine
            check(foreign["sessions"] == [], "another user can't read my task's history")

        if STAGE >= 3:
            await js("document.getElementById('closeCardModalBtn').click()", wait=1.0)
            # Reports: reload lands there, loads once, never shows Calendario first
            await js("document.getElementById('tabReports').click()", wait=1.5)
            stored = await js("localStorage.getItem('last_view')")
            await b.send("Page.addScriptToEvaluateOnNewDocument", source="""
                document.addEventListener('DOMContentLoaded', () => {
                    window.__firstView = typeof currentViewIndex !== 'undefined' ? currentViewIndex : null;
                    window.__firstTransform = document.getElementById('viewsTrack').style.transform;
                });""")
            await b.goto(BASE + "/", wait=3.0)
            r = await js("""({view: currentViewIndex, first: window.__firstView, firstT: window.__firstTransform,
                sel: document.getElementById('tabReports').getAttribute('aria-selected'),
                cards: document.querySelectorAll('#reportsBody .report-card').length,
                reqs: performance.getEntriesByType('resource').filter(e => e.name.includes('/api/pomodoro?date_from')).length})""")
            check(stored == "2" and r["view"] == 2 and r["sel"] == "true", f"reload stays on Reportes ({stored}, {r})")
            check(r["first"] == 2 and r["firstT"] == "translateX(-200%)", f"already on Reportes before the first paint ({r['first']}, {r['firstT']})")
            check(r["cards"] >= 5 and r["reqs"] == 2, f"reports load once on reload ({r['cards']} cards, {r['reqs']} session requests)")

            # Tableros: reload keeps it and the wide board layout
            await js("document.getElementById('tabProjects').click()", wait=1.0)
            await b.goto(BASE + "/", wait=3.0)
            r = await js("({view: currentViewIndex, wide: document.body.classList.contains('board-wide'), cards: document.querySelectorAll('.board-card').length, doc: document.documentElement.scrollHeight, h: document.getElementById('viewProjects').offsetHeight})")
            check(r["view"] == 1 and r["wide"] and r["cards"] > 0, f"reload stays on Tableros, wide and loaded ({r})")

            # Calendario: back to the default
            await js("document.getElementById('tabCalendar').click()", wait=0.8)
            await b.goto(BASE + "/", wait=2.5)
            check(await js("currentViewIndex") == 0, "reload on Calendario stays there")

            # A bad stored value falls back to Calendario
            await js("localStorage.setItem('last_view', '7')")
            await b.goto(BASE + "/", wait=2.5)
            check(await js("currentViewIndex") == 0, "an invalid stored tab falls back to Calendario")

            # Logout forgets it
            await js("document.getElementById('tabReports').click()", wait=0.8)
            await js("handleLogout()", wait=1.5)
            r = await js("({stored: localStorage.getItem('last_view'), view: currentViewIndex})")
            check(r["stored"] is None and r["view"] == 0, f"logout forgets the tab ({r})")

        print("\n".join(results))
    finally:
        await b.close()

    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_card_history():
    asyncio.run(main())
