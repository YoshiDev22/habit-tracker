"""Cerrar sesión con el cronómetro corriendo no pierde ni infla el tiempo.

1. Pasado el tope de 8 h, se guarda recortado a 8 h y con la nota de cierre
   automático (por revisar), no lo que marque el reloj.
2. Con el token vencido (cierre de sesión automático por 401), el guardado falla:
   la sesión queda en la cola con su dueño y se envía cuando él vuelve a entrar.
3. Otra cuenta en el mismo dispositivo no envía la cola ajena.
"""
import asyncio
import json

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
AUTOCLOSE = "Cerrado automáticamente a las 8 h"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def start_stopwatch(b, task, minutes_ago):
    await b.js(f"startTimerForTask({task['project_id']}, {task['id']}, 'stopwatch', {json.dumps(task['title'])})")
    await b.wait_for("pomoState.status === 'running'")
    await b.js(f"pomoState.startedEpochMs = Date.now() - {minutes_ago} * 60000; savePomoState();")


def sessions_of(task_id):
    _, data = call("GET", f"/api/pomodoro?task_id={task_id}", expect=200)
    return data["sessions"]


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    _, me = call("GET", "/api/auth/me", expect=200)
    _, tl = call("GET", "/api/tasks", expect=200)
    task = next(t for t in tl["tasks"] if not t["is_done"])
    before = len(sessions_of(task["id"]))

    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # 1. Diez horas corriendo y cerrar sesión: 8 h y por revisar
        await start_stopwatch(b, task, 10 * 60)
        await b.js("document.getElementById('logoutBtn').click()")
        await asyncio.sleep(1.5)
        saved = sessions_of(task["id"])
        new = saved[0] if len(saved) == before + 1 else None
        check(new is not None and new["duration_seconds"] == 8 * 3600 and new["note"] == AUTOCLOSE,
              f"logout past the cap saves 8 h, marked for review ({new and (new['duration_seconds'], new['note'])})")

        # 2. Token vencido: el 401 cierra la sesión; lo medido va a la cola con su dueño
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await start_stopwatch(b, task, 3)
        await b.js("localStorage.setItem('access_token', 'vencido'); apiFetch('/api/auth/me').catch(() => {})")
        await asyncio.sleep(1.5)
        queue = await b.js("JSON.parse(localStorage.getItem('pomodoro_pending') || '[]')")
        check(len(queue) == 1 and queue[0]["owner"] == me["id"] and 170 <= queue[0]["payload"]["duration_seconds"] <= 200,
              f"an expired-token logout keeps the time queued with its owner ({queue})")
        check(len(sessions_of(task["id"])) == before + 1, "nothing was saved yet")
        check(await b.js("pomoState.status") == "idle" and await b.js("!getToken()"), "the app logged out once, timer released")

        # 3. Otra cuenta entra en este dispositivo: no envía la cola ajena
        login("visita@test.com")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(api.TOKEN)});")
        await b.goto(BASE + "/", wait=3.0)
        left = await b.js("JSON.parse(localStorage.getItem('pomodoro_pending') || '[]').length")
        login("yoshi@test.com")
        check(left == 1 and len(sessions_of(task["id"])) == before + 1, f"another account leaves it alone ({left} queued)")
        await b.js("localStorage.removeItem('access_token')")

        # Vuelve el dueño: se envía y la cola queda vacía
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=3.0)
        await b.wait_for("!localStorage.getItem('pomodoro_pending')")
        saved = sessions_of(task["id"])
        check(len(saved) == before + 2 and any(170 <= s["duration_seconds"] <= 200 for s in saved),
              f"its owner sends it on the next visit ({[s['duration_seconds'] for s in saved]})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith("[exception]")]
    print("exceptions:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_logout_timer():
    asyncio.run(main())
