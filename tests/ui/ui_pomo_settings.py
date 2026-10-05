"""Pomodoro durations in ⚙️ Configuración › Pomodoro; a running timer keeps the one it started with."""
import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

TITLE = "Idea suelta sin proyecto"
SETTINGS_OPEN = "!document.getElementById('habitsSetupModal').classList.contains('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    token, _ = seed()
    task = next(t for t in call("GET", "/api/tasks", expect=200)[1]["tasks"] if t["title"] == TITLE)
    b = Browser()
    await b.start()

    async def js(expr, wait=0.0):
        r = await b.js(expr)
        if wait:
            await asyncio.sleep(wait)
        return r

    async def save_settings(focus, short, long):
        await js("openSettings('pomodoro')")
        await b.wait_for(SETTINGS_OPEN)
        await js(f"document.getElementById('configPomoFocus').value = '{focus}';"
                 f"document.getElementById('configPomoShort').value = '{short}';"
                 f"document.getElementById('configPomoLong').value = '{long}';"
                 "document.querySelector('#configPomoForm .submit-btn').click()")
        await b.wait_for("document.getElementById('configPomoStatus').textContent === 'Guardado ✓'")
        await js("document.getElementById('settingsClose').click()", wait=0.5)

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        # Limpio: el navegador se reusa entre pruebas, y otra en el mismo puerto
        # pudo dejar festivos (vacíos, sin internet) en work_calendar_cache
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        await js("document.getElementById('tabProjects').click()", wait=1.0)
        # The profile no longer has them
        await js("showProfile()", wait=0.4)
        in_profile = await js("!!document.querySelector('#profileModal input[type=number]')")
        check(not in_profile, "the profile no longer has the pomodoro fields")
        await js("closeProfileModal()", wait=0.3)

        # Organizar -> Configurar pomodoro lleva a Configuración › Pomodoro, placeholders = defaults
        await js("document.getElementById('boardConfigBtn').click()", wait=1.0)
        await js("document.getElementById('configPomoOpen').click()")
        await b.wait_for(SETTINGS_OPEN)
        st = await js("""({organizar: !document.getElementById('boardConfigModal').classList.contains('hidden'),
            pomoOpen: document.querySelector('#habitsSetupModal [data-section="pomodoro"]').classList.contains('active'),
            fields: ['configPomoFocus','configPomoShort','configPomoLong'].map(id => [document.getElementById(id).value, document.getElementById(id).placeholder])})""")
        check(not st["organizar"] and st["pomoOpen"], f"Organizar's button opens Configuración › Pomodoro ({st})")
        check(st["fields"] == [["", "25"], ["", "5"], ["", "15"]], f"defaults as placeholders ({st['fields']})")
        await b.shot("config_pomo", full=False)
        await js("document.getElementById('settingsClose').click()", wait=0.5)

        # A pomodoro started with the default keeps it after the setting changes
        await js(f"startTimerForTask({task['project_id']}, {task['id']}, 'focus', {json.dumps(TITLE)})", wait=0.5)
        await save_settings(50, 10, 30)
        _, me = call("GET", "/api/auth/me", expect=200)
        running = await js("pomoState.plannedSeconds")
        check((me["pomodoro_focus_seconds"], me["pomodoro_short_break_seconds"], me["pomodoro_long_break_seconds"]) == (3000, 600, 1800),
              f"profile saves 50/10/30 in seconds ({me['pomodoro_focus_seconds']}, {me['pomodoro_short_break_seconds']}, {me['pomodoro_long_break_seconds']})")
        check(running == 1500, f"the running pomodoro keeps its 25 min ({running})")

        # Finishing it offers the new break lengths
        await js("pomoState.startedEpochMs = Date.now() - 1500000 + 500; pomoState.targetEpochMs = Date.now() + 500; savePomoState();", wait=3.0)
        actions = await js("[...pomodoroBarActions.querySelectorAll('button')].map(b => b.textContent)")
        check(actions[:2] == ["Descanso 10 min", "30 min"], f"break offer uses the new lengths ({actions})")
        await js("[...pomodoroBarActions.querySelectorAll('button')].find(b => b.textContent === '30 min').click()", wait=0.8)
        brk = await js("[pomoState.mode, pomoState.plannedSeconds, pomoClockText()]")
        check(brk[0] == "long_break" and brk[1] == 1800 and brk[2] in ("30:00", "29:59"), f"long break lasts 30 min ({brk})")
        await js("stopTimer()", wait=0.8)

        # A new pomodoro starts with 50 min, and survives a reload with it
        await js(f"startTimerForTask({task['project_id']}, {task['id']}, 'focus', {json.dumps(TITLE)})", wait=0.8)
        st = await js("[pomoState.plannedSeconds, pomoClockText()]")
        check(st[0] == 3000 and st[1] in ("50:00", "49:59"), f"new pomodoro starts at 50 min ({st})")
        await b.goto(BASE + "/", wait=2.5)
        st = await js("pomoState.plannedSeconds")
        check(st == 3000, f"after a reload the running pomodoro still has 50 min ({st})")
        await js("stopTimer({ skipConfirm: true })", wait=1.0)

        # Out of range is refused, and saving confirms in place
        await js("openSettings('pomodoro')")
        await b.wait_for(SETTINGS_OPEN)
        await js("document.getElementById('configPomoFocus').value = '0'; document.getElementById('configPomoForm').requestSubmit()", wait=0.5)
        err = await js("!document.getElementById('configPomoError').classList.contains('hidden') || !document.getElementById('configPomoFocus').checkValidity()")
        check(err, "0 minutes is refused")
        await js("document.getElementById('configPomoFocus').value = '50'; document.querySelector('#configPomoForm .submit-btn').click()", wait=1.2)
        st = await js("({open: !document.getElementById('habitsSetupModal').classList.contains('hidden'), status: document.getElementById('configPomoStatus').textContent})")
        check(st == {"open": True, "status": "Guardado ✓"}, f"saving says 'Guardado ✓' and stays open ({st})")
        await js("document.getElementById('settingsClose').click()", wait=0.5)

        # Clearing the fields goes back to the defaults
        await save_settings("", "", "")
        _, me = call("GET", "/api/auth/me", expect=200)
        check(me["pomodoro_focus_seconds"] is None and me["pomodoro_long_break_seconds"] is None, "empty fields reset to the defaults")
        await js(f"startTimerForTask({task['project_id']}, {task['id']}, 'focus', {json.dumps(TITLE)})", wait=0.5)
        check(await js("pomoState.plannedSeconds") == 1500, "and a new pomodoro is 25 min again")
        await js("stopTimer({ skipConfirm: true })", wait=0.8)


    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_pomo_settings():
    asyncio.run(main())
