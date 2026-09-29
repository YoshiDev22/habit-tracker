"""Modal de hábitos: un hábito nuevo trae un color libre, repetir color avisa sin
bloquear, y borrar dice cuánto cambian la racha y el récord."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()


async def main():
    login("colores@test.com")
    token = api.TOKEN
    call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura", "color": "#3498db"}, expect=201)
    _, gym = call("POST", "/api/habits/definitions", {"key": "gymx", "label": "Pesas", "color": "#27ae60"}, expect=201)
    _, oculto = call("POST", "/api/habits/definitions", {"key": "oculto", "label": "Oculto", "color": "#9b59b6"}, expect=201)
    # Lectura hace 3 días y ayer; Oculto solo hace 2: borrar Oculto corta la racha
    for i, key in ((3, "lectura"), (2, "oculto"), (1, "lectura")):
        call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i)}", {"habit_key": key, "done": True}, expect=200)
    call("PATCH", f"/api/habits/definitions/{oculto['id']}", {"is_active": False}, expect=200)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    rows = "[...document.querySelectorAll('#habitsOptions .habit-option')].map(r => [r.dataset.habitKey, r.querySelector('input[type=color]').value])"
    warning = "(() => { const w = document.getElementById('setupColorWarning'); return w.classList.contains('hidden') ? '' : w.textContent; })()"

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('settingsBtn').click()")
        await b.wait_for("document.querySelectorAll('#habitsOptions .habit-option').length", lambda n: n == 2)

        # Tomados: azul y verde (activos) y morado (el oculto). El propio arranca en el primero libre
        custom = await b.js("document.getElementById('customHabitColor').value")
        check(custom == "#e74c3c", f"a new habit of your own starts with a free color ({custom})")
        check(await b.js(warning) == "", "no warning when every color is different")

        # Dieta sugiere verde, que ya usa Pesas: se le da el siguiente libre
        await b.js("document.querySelector('.habit-suggestion[data-habit-key=\"dieta\"]').click()")
        r = await b.js(rows)
        check(r[-1] == ["dieta", "#e74c3c"], f"a suggestion whose color is taken gets a free one ({r[-1]})")
        custom = await b.js("document.getElementById('customHabitColor').value")
        check(custom == "#f39c12", f"the next free color moves on for your own ({custom})")

        # Repetir a propósito: avisa, y se puede guardar
        await b.js("""(() => { const i = [...document.querySelectorAll('#habitsOptions .habit-option')]
            .find(r => r.dataset.habitKey === 'dieta').querySelector('input[type=color]');
            i.value = '#3498db'; i.dispatchEvent(new Event('input', {bubbles: true})); })()""")
        w = await b.js(warning)
        check("Lectura y Dieta tienen el mismo color" in w, f"repeating a color warns ({w})")
        await b.shot("setup_color_warning", full=False)
        await b.js("document.getElementById('saveHabitsBtn').click()")
        await b.wait_for("!document.getElementById('confirmModal').classList.contains('hidden')", bool)
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await b.wait_for("document.getElementById('habitsSetupModal').classList.contains('hidden')", bool)
        _, defs = call("GET", "/api/habits/definitions", expect=200)
        colors = {h["key"]: h["color"] for h in defs["habits"]}
        check(colors.get("dieta") == "#3498db" == colors.get("lectura"), f"the repeated color is saved anyway ({colors})")

        # Borrar el oculto: la confirmación dice cuánto baja la racha
        await b.js("document.getElementById('settingsBtn').click()")
        await b.wait_for("document.querySelectorAll('#archivedHabitsList .archived-row').length", lambda n: n == 1)
        await b.js("document.querySelector('#archivedHabitsList .archived-delete').click()")
        msg = await b.wait_for("(() => { const m = document.getElementById('confirmModal'); return m.classList.contains('hidden') ? '' : document.getElementById('confirmModalMessage').textContent; })()", bool)
        check("Se borrará su único registro" in msg and "Tu racha pasaría de 3 días a 1 día" in msg
              and "tu récord, de 3 días a 1 día" in msg, f"the delete confirmation shows the impact ({msg})")
        await b.shot("delete_impact_confirm", full=False)
        await b.js("document.getElementById('confirmModalCancelBtn').click()")
        await asyncio.sleep(0.5)
        _, st = call("GET", f"/api/habits/streak?today={TODAY}", expect=200)
        check(st["streak"] == 3, "cancelling keeps everything")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_habit_setup_colors():
    asyncio.run(main())
