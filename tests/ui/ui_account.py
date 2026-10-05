"""Mi perfil › Cambiar contraseña y Borrar mi cuenta (Irme 30 días, Borrar ahora)."""
import asyncio
import json

import api
from api import call, login, wait_api
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
CONFIRM_OPEN = "!document.getElementById('confirmModal').classList.contains('hidden')"
AUTH_SHOWN = "!document.getElementById('authScreen').classList.contains('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def enter(b, token):
    await b.goto(BASE + "/")
    await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
    await b.goto(BASE + "/", wait=2.5)


async def open_section(b, page):
    """Mi perfil es un menú de desglose: se abre en el menú y la fila lleva a su página."""
    await b.js("document.getElementById('userEmail').click()")
    await b.wait_for("!document.getElementById('profileMenu').hidden && !document.getElementById('profileModal').classList.contains('hidden')")
    await b.js(f"document.querySelector('#profileMenu [data-open={page}]').click()")


async def main():
    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)

        # Cambiar la contraseña
        login("yoshi@test.com")
        await enter(b, api.TOKEN)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('userEmail').click()")
        await b.wait_for("!document.getElementById('profileModal').classList.contains('hidden')")
        st = await b.js("({menu: !document.getElementById('profileMenu').hidden, title: document.getElementById('profileTitle').textContent,"
                        " rows: [...document.querySelectorAll('#profileMenu [data-open]')].map(r => r.dataset.open)})")
        check(st == {"menu": True, "title": "Mi perfil", "rows": ["profile", "password", "delete"]},
              f"Mi perfil opens on its menu ({st})")
        await b.shot("profile_menu", full=False)
        await b.js("document.querySelector('#profileMenu [data-open=password]').click()")
        st = await b.js("({menu: document.getElementById('profileMenu').hidden, title: document.getElementById('profileTitle').textContent,"
                        " back: !document.getElementById('profileBack').hidden})")
        check(st == {"menu": True, "title": "Cambiar contraseña", "back": True}, f"a row slides into its page ({st})")
        await b.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
        check(await b.js("!document.getElementById('profileMenu').hidden"), "Escape goes back to the menu")
        await b.js("document.querySelector('#profileMenu [data-open=password]').click()")
        fill = """(() => {{ document.getElementById('passwordCurrent').value = {0};
            document.getElementById('passwordNew').value = {1};
            document.getElementById('passwordRepeat').value = {2};
            document.getElementById('passwordForm').requestSubmit(); }})()"""
        await b.js(fill.format(json.dumps(api.PASSWORD), json.dumps("nueva-123"), json.dumps("otra-123")))
        err = await b.js("document.getElementById('passwordError').textContent")
        check("no coinciden" in err, f"mismatched new passwords are caught ({err})")
        await b.js(fill.format(json.dumps("mala"), json.dumps("nueva-123"), json.dumps("nueva-123")))
        await b.wait_for("!document.getElementById('passwordError').classList.contains('hidden')")
        err = await b.js("document.getElementById('passwordError').textContent")
        check("no es correcta" in err, f"a wrong current password says so ({err})")
        await b.js(fill.format(json.dumps(api.PASSWORD), json.dumps("nueva-123"), json.dumps("nueva-123")))
        await b.wait_for("document.getElementById('passwordStatus').textContent === 'Contraseña cambiada ✓'")
        check(await b.js("!!localStorage.getItem('access_token')"), "the password changes and this session stays")
        await b.shot("account_password", full=False)
        login("yoshi@test.com", "nueva-123")
        check(bool(api.TOKEN), "logging in with the new password works")

        # Irme 30 días: se cierra la sesión
        await enter(b, api.TOKEN)
        await b.js(CLOSE_WELCOME)
        await open_section(b, "delete")
        await b.js("document.getElementById('leaveLaterBtn').click()")
        st = await b.js("({form: !document.getElementById('deleteForm').hidden, confirm: document.getElementById('deleteConfirmGroup').hidden,"
                        " logout: !document.getElementById('deleteLogoutGroup').hidden})")
        check(st == {"form": True, "confirm": True, "logout": True}, f"'Irme 30 días' asks for the password only ({st})")
        await b.js("document.getElementById('deletePassword').value = 'nueva-123'; document.getElementById('deleteForm').requestSubmit()")
        await b.wait_for(CONFIRM_OPEN)
        msg = await b.js("document.getElementById('confirmModalMessage').textContent")
        check("se borrará el" in msg, f"it says when the account will be deleted ({msg})")
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await b.wait_for(AUTH_SHOWN)
        # Con la casilla marcada se cerraron las otras sesiones: también la de la API
        check(call("GET", "/api/auth/me")[0] == 401, "the other sessions were closed")
        login("yoshi@test.com", "nueva-123")
        _, me = call("GET", "/api/auth/me", expect=200)
        check(me["delete_after"] is not None, "the deletion is scheduled")

        # Al volver: conservarla
        login("yoshi@test.com", "nueva-123")
        await enter(b, api.TOKEN)
        await b.wait_for(CONFIRM_OPEN)
        msg = await b.js("document.getElementById('confirmModalMessage').textContent")
        check("¿Quieres conservarla?" in msg, f"coming back asks whether to keep the account ({msg})")
        await b.shot("account_keep", full=False)
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await wait_api("/api/auth/me", lambda body: body["delete_after"] is None)
        check(await b.js("document.getElementById('authScreen').classList.contains('hidden')"), "keeping it stays in the app")

        # Borrar ahora, con otra cuenta
        call("POST", "/api/auth/register", {"email": "se-va@test.com", "password": api.PASSWORD})
        login("se-va@test.com")
        await enter(b, api.TOKEN)
        await b.js(CLOSE_WELCOME)
        await open_section(b, "delete")
        await b.js("document.getElementById('deleteNowBtn').click()")
        await b.js("document.getElementById('deletePassword').value = 'secret123'; document.getElementById('deleteConfirm').value = 'nop';"
                   " document.getElementById('deleteForm').requestSubmit()")
        await b.wait_for("!document.getElementById('deleteError').classList.contains('hidden')")
        err = await b.js("document.getElementById('deleteError').textContent")
        check("BORRAR" in err, f"'Borrar ahora' needs the word ({err})")
        await b.js("document.getElementById('deleteConfirm').value = 'BORRAR'; document.getElementById('deleteForm').requestSubmit()")
        await b.wait_for(CONFIRM_OPEN)
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await b.wait_for(AUTH_SHOWN)
        status, _ = call("POST", "/api/auth/login", form={"username": "se-va@test.com", "password": api.PASSWORD})
        check(status == 401, f"the account is gone ({status})")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"fits a phone ({wide}px)")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_account():
    asyncio.run(main())
