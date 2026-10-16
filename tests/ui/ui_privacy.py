"""Aviso de privacidad (1.28): la página /privacidad y sus enlaces (registro, pantalla de
entrar y Mi perfil). El servidor de prueba no tiene PRIVACY_*: la página lo dice."""
import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)

        # Sin cuenta: el pie de la pantalla de entrar y la nota del registro
        await b.goto(BASE + "/")
        href = await b.js("document.querySelector('#authScreen .auth-privacy a').getAttribute('href')")
        check(href == "/privacidad", f"the sign-in screen links the notice ({href})")
        await b.js("document.getElementById('showRegisterBtn').click()")
        await b.wait_for("!document.getElementById('registerModal').classList.contains('hidden')")
        st = await b.js("""(() => { const note = document.getElementById('registerPrivacy');
            const submit = document.querySelector('#registerForm button[type=submit]');
            return {href: note.querySelector('a').getAttribute('href'), text: note.textContent.replace(/\\s+/g, ' '),
                    before: !!(note.compareDocumentPosition(submit) & Node.DOCUMENT_POSITION_FOLLOWING)}; })()""")
        check(st["href"] == "/privacidad" and st["before"] and "propio riesgo" in st["text"],
              f"the sign-up form shows the notice before 'Crear Cuenta' ({st})")
        await b.shot("privacy_register", full=False)

        # La página: sin sesión, cabe en el teléfono, y avisa que falta el contacto
        await b.goto(BASE + "/privacidad")
        st = await b.js("""({title: document.querySelector('h1').textContent,
            sections: [...document.querySelectorAll('.privacy-page h2')].map(h => h.textContent),
            missing: !!document.querySelector('.privacy-missing'),
            wide: document.documentElement.scrollWidth})""")
        check(st["title"] == "Aviso de privacidad" and st["missing"] and st["wide"] <= 390
              and st["sections"][:2] == ["Responsable", "Qué datos tratamos"] and "Proyecto en desarrollo" in st["sections"],
              f"the notice opens without a session and fits a phone ({st})")
        await b.shot("privacy_page", full=True)

        # Con sesión: Mi perfil › Aviso de privacidad abre la página en otra pestaña
        await b.goto(BASE + "/api/health")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('habitsSetupModal').classList.add('hidden')")
        await b.js("document.getElementById('userEmail').click()")
        await b.wait_for("!document.getElementById('profileModal').classList.contains('hidden')")
        st = await b.js("""(() => { const row = document.getElementById('profilePrivacy');
            return {href: row.getAttribute('href'), target: row.target, visible: row.offsetHeight > 0}; })()""")
        check(st == {"href": "/privacidad", "target": "_blank", "visible": True},
              f"Mi perfil has a row that opens the notice in a new tab ({st})")
        await b.shot("privacy_profile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_privacy():
    asyncio.run(main())
