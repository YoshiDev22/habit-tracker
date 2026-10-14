"""Mi perfil › Reportar un problema (1.27): la vista previa enseña exactamente lo que se envía."""
import asyncio
import json

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
PREVIEW = "document.getElementById('feedbackPreview').textContent"
STATUS = "document.getElementById('feedbackStatus').textContent"
ERROR = "(() => { const e = document.getElementById('feedbackError'); return e.classList.contains('hidden') ? '' : e.textContent; })()"
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
        await b.goto(BASE + "/api/health")   # mismo origen, sin arrancar la app
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        # Un error y una promesa rechazada de esta sesión (eventos sintéticos: no ensucian la consola)
        await b.js("""window.dispatchEvent(new ErrorEvent('error', {message: 'TypeError: boom-prueba',
                filename: location.origin + '/board.js?v=9', lineno: 7}));
            window.dispatchEvent(new PromiseRejectionEvent('unhandledrejection',
                {promise: Promise.resolve(), reason: new Error('falló la red')}));""")
        # Lo que la página manda a /api/feedback, tal cual
        await b.js("""window._sent = []; const f = window.fetch;
            window.fetch = (u, o) => { if (String(u).includes('/api/feedback')) window._sent.push(JSON.parse(o.body));
                return f(u, o); };""")

        await b.js("document.getElementById('userEmail').click()")
        await b.wait_for("!document.getElementById('profileMenu').hidden && !document.getElementById('profileModal').classList.contains('hidden')")
        await b.js("document.querySelector('#profileMenu [data-open=feedback]').click()")
        preview = await b.wait_for(PREVIEW, lambda v: "boom-prueba" in (v or ""))
        shown = json.loads(preview)
        version = await b.js("document.getElementById('mainVersion').textContent.trim()")
        check(shown["version"] == version and shown["view"] and "×" in shown["screen"] and shown["user_agent"],
              f"the preview shows version, tab, screen and browser ({ {k: shown[k] for k in ('version', 'view', 'screen')} })")
        check(shown["errors"] == ["TypeError: boom-prueba (board.js:7)", "Error: falló la red"],
              f"and this session's errors, with only the file name ({shown['errors']})")
        check(token not in preview and "access_token" not in preview, "no token in what is sent")
        check(await b.js("document.activeElement.id") == "feedbackText", "the text gets the focus")

        # Demasiado corto: se dice por qué y no se envía nada
        await b.js("document.getElementById('feedbackText').value = 'corto'")
        await b.js("document.getElementById('feedbackForm').requestSubmit()")
        err = await b.wait_for(ERROR, bool)
        check("10 caracteres" in err and await b.js("window._sent.length") == 0, f"too short is refused before sending ({err})")

        # Enviar con detalles: va justo lo de la vista previa
        text = "El tablero se queda en blanco al cambiar de pestaña"
        await b.js(f"""(() => {{ const t = document.getElementById('feedbackText'); t.value = {json.dumps(text)};
            t.dispatchEvent(new Event('input')); }})()""")
        check(await b.js("document.getElementById('feedbackCount').textContent") == f"{len(text)} / 2000", "counts the characters")
        preview_now = json.loads(await b.js(PREVIEW))
        await b.js("document.getElementById('feedbackForm').requestSubmit()")
        status = await b.wait_for(STATUS, lambda v: "Gracias" in (v or ""))
        sent = await b.js("window._sent")
        check("Gracias" in status and sent == [{"text": text, "details": preview_now}],
              f"what is sent is exactly the text and the preview ({status})")
        check(await b.js("document.getElementById('feedbackText').value") == "", "the text clears after sending")
        await b.shot("feedback_page", full=False)

        # Sin detalles: la vista previa se oculta y no van
        await b.js("document.getElementById('feedbackDetailsOn').click()")
        check(await b.js("document.getElementById('feedbackDetails').hidden"), "unchecking hides the preview")
        await b.js("""document.getElementById('feedbackText').value = 'Otro problema, sin detalles';
            document.getElementById('feedbackForm').requestSubmit()""")
        await b.wait_for("window._sent.length === 2")
        check(await b.js("window._sent[1]") == {"text": "Otro problema, sin detalles", "details": None},
              "without details, only the text goes")
        check(not await b.js("document.documentElement.scrollWidth > window.innerWidth"), "fits a phone without sideways scroll")

        # Pasado el límite del día, el motivo se enseña tal cual
        for i in range(3):
            call("POST", "/api/feedback", {"text": f"Reporte de relleno {i}"}, expect=201)
        await b.js("""document.getElementById('feedbackText').value = 'Uno más de la cuenta';
            document.getElementById('feedbackForm').requestSubmit()""")
        err = await b.wait_for(ERROR, bool)
        check("mañana" in err, f"over the daily limit it says so ({err})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_feedback():
    asyncio.run(main())
