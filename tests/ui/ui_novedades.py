"""Novedades (1.25): la ventana al entrar después de actualizar y Mi perfil ›
Novedades. El servidor de prueba arranca sin Novedades (conftest); aquí se le
dan las suyas reemplazando la respuesta de /api/novedades."""
import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE
results = []
DATA = {"current": "9.2.0", "versions": [
    {"version": "9.2.0", "date": "2026-10-09", "sections": [
        {"title": "Nuevas funciones", "items": ["**Notas por día**: en el calendario, toca ✎ junto a un hábito."]},
        {"title": "Cambios", "items": ["**Algo más claro**: un cambio."]}]},
    {"version": "9.1.0", "date": "2026-10-01", "sections": [
        {"title": "Nuevas funciones", "items": ["**Lo de antes**: otra cosa."]}]},
]}
MODAL_OPEN = "!document.getElementById('novedadesModal').classList.contains('hidden')"


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()
    stub = f"""(() => {{ const real = window.apiFetch;
        window.apiFetch = (path, options) => path === '/api/novedades'
            ? Promise.resolve(JSON.parse({json.dumps(json.dumps(DATA))})) : real(path, options); }})()"""
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('habitsSetupModal').classList.add('hidden')")
        check(await b.js("document.getElementById('novedadesModal').classList.contains('hidden')"),
              "with no Novedades for this version, no window")

        # Vio la 9.0: ve la 9.1 y la 9.2, juntas
        await b.js(stub)
        await b.js("localStorage.setItem('novedades_seen', '9.0.0'); loadNovedades()")
        await b.wait_for(MODAL_OPEN)
        st = await b.js("""({title: document.getElementById('novedadesTitle').textContent,
            versions: document.querySelectorAll('#novedadesBody .novedades-version').length,
            bold: document.querySelector('#novedadesBody strong').textContent,
            text: document.getElementById('novedadesBody').textContent})""")
        check(st["title"] == "Novedades hasta la 9.2" and st["versions"] == 2 and st["bold"] == "Notas por día"
              and "Para actualizar" not in st["text"], f"the versions not seen yet, in bold and without deploy notes ({st['title']})")
        await b.shot("novedades_window", full=False)
        await b.js("document.getElementById('novedadesOk').click()")
        check(await b.js("localStorage.getItem('novedades_seen')") == "9.2.0", "closing it marks the version as seen")

        # Ya vista: no sale otra vez
        await b.js("loadNovedades()")
        await asyncio.sleep(0.5)
        check(await b.js("document.getElementById('novedadesModal').classList.contains('hidden')"), "seen: it doesn't show again")

        # Sin registro en este dispositivo: solo la actual
        await b.js("localStorage.removeItem('novedades_seen'); loadNovedades()")
        await b.wait_for(MODAL_OPEN)
        st = await b.js("({title: document.getElementById('novedadesTitle').textContent,"
                        " versions: document.querySelectorAll('#novedadesBody .novedades-version').length})")
        check(st == {"title": "Novedades de la 9.2", "versions": 1}, f"first time on this device: only the current one ({st})")
        await b.js("document.getElementById('novedadesClose').click()")

        # Recién registrado: empieza al día, sin ventana
        await b.js("localStorage.removeItem('novedades_seen'); sessionStorage.setItem('novedades_just_registered', '1'); loadNovedades()")
        await asyncio.sleep(0.5)
        check(await b.js("document.getElementById('novedadesModal').classList.contains('hidden')")
              and await b.js("localStorage.getItem('novedades_seen')") == "9.2.0", "a new account starts up to date")

        # Mi perfil › Novedades: todas
        await b.js("document.getElementById('userEmail').click()")
        await b.wait_for("!document.getElementById('profileModal').classList.contains('hidden')")
        await b.js("document.querySelector('#profileMenu [data-open=news]').click()")
        st = await b.js("({title: document.getElementById('profileTitle').textContent,"
                        " versions: [...document.querySelectorAll('#novedadesPage .novedades-version-title')].map(t => t.textContent)})")
        check(st == {"title": "Novedades", "versions": ["Versión 9.2", "Versión 9.1"]}, f"Mi perfil › Novedades lists them all ({st})")
        await b.shot("novedades_profile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_novedades():
    asyncio.run(main())
