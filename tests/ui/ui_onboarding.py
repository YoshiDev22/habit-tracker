import asyncio
import json
import sys

import api
from api import call, login
from cdp import Browser
from ui_board import CLOSE_WELCOME, BASE


async def main():
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    # Backend: a brand-new user has no board; the existing user keeps "Mi tablero"
    login("yoshi@test.com")
    _, bl = call("GET", "/api/boards", expect=200)
    check([b["name"] for b in bl["boards"]] == ["Mi tablero"], "existing user with tasks still gets 'Mi tablero'")

    login("api-nuevo@test.com")
    _, bl = call("GET", "/api/boards", expect=200)
    check(bl["total"] == 0, "new user without tasks starts with no board")
    _, t = call("POST", "/api/tasks", {"title": "primera"}, expect=201)
    _, bl = call("GET", "/api/boards", expect=200)
    check([b["name"] for b in bl["boards"]] == ["Mi tablero"] and t["board_id"] == bl["boards"][0]["id"],
          "creating a task with no board creates 'Mi tablero' on the spot")

    # UI with a brand-new user
    login("nuevo@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()

    async def js(expr, wait=0.8):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    modal_open = "!document.getElementById('boardOnboardingModal').classList.contains('hidden')"

    async def settle():
        # Wait for the app to finish booting (board loaded, habits welcome shown)
        for _ in range(40):
            if await b.js("boardState.loaded && !document.getElementById('habitsSetupModal').classList.contains('hidden')"):
                break
            await asyncio.sleep(0.25)
        await b.js(CLOSE_WELCOME)
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('board_selected'); localStorage.removeItem('projects_view');")
        await b.goto(BASE + "/", wait=1.0)
        await settle()
        check(not await b.js(modal_open), "no prompt while on Calendario")

        await js("document.getElementById('tabProjects').click()", wait=1.0)
        st = await b.js(f"({{open: {modal_open}, focus: document.activeElement.id}})")
        check(st == {"open": True, "focus": "boardOnboardingName"}, f"entering Tableros with no board offers the first one ({st})")
        await b.shot("onboarding", full=False)

        await js("document.getElementById('boardOnboardingSkip').click()", wait=0.8)
        check(await b.js(f"!({modal_open}) && currentViewIndex === 0"), "Omitir closes it and goes back to Calendario")

        await js("document.getElementById('tabProjects').click()", wait=1.0)
        check(await b.js(modal_open), "it is offered again next time")
        await b.send("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        await asyncio.sleep(0.8)
        check(await b.js(f"!({modal_open}) && currentViewIndex === 0"), "Escape behaves like Omitir")

        await js("document.getElementById('tabProjects').click()", wait=1.0)
        await js("document.getElementById('boardOnboardingName').value = 'Trabajo'; document.getElementById('boardOnboardingForm').requestSubmit()", wait=2.0)
        st = await b.js(f"({{open: {modal_open}, view: currentViewIndex, boards: [...document.querySelectorAll('#boardSelect option')].map(o => o.textContent), columns: [...document.querySelectorAll('.board-column-name')].map(e => e.textContent)}})")
        check(st == {"open": False, "view": 1, "boards": ["Trabajo", "＋ Nuevo tablero…"], "columns": ["Por hacer", "Haciendo", "Hecho"]},
              f"Crear makes the board and shows it ({st})")

        await js("document.getElementById('tabCalendar').click()", wait=0.5)
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        check(not await b.js(modal_open), "no more prompt once there is a board")

        # Empty name uses the placeholder
        login("nuevo2@test.com")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(api.TOKEN)}); localStorage.removeItem('board_selected');")
        await b.goto(BASE + "/", wait=1.0)
        await settle()
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        await js("document.getElementById('boardOnboardingForm').requestSubmit()", wait=2.0)
        name = await b.js("document.getElementById('boardSelect').selectedOptions[0].textContent")
        check(name == "Mi tablero", f"empty name creates 'Mi tablero' ({name})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_onboarding():
    asyncio.run(main())
