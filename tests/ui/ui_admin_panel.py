"""El panel de administración en el navegador (1.27, Fase 1), arrancado con
scripts/admin_dev.py como lo hace Yoshio en su máquina."""
import asyncio
import os
import tempfile
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

import api
from api import call, login
from cdp import Browser

ROOT = Path(__file__).resolve().parents[2]
ADMIN = "yoshi@test.com"
XSS = "<img src=x onerror=\"window.__pwned=1\"><script>window.__pwned=2</script> el tablero se rompió"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_panel(db):
    """scripts/admin_dev.py sobre la base de esta prueba; devuelve (proceso, enlace, salida)."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8",
           "PYTHONUNBUFFERED": "1",
           # ni proveedor de IA, aunque backend/.env lo tenga (como la app en las pruebas)
           "AI_PROVIDER": "", "AI_BASE_URL": "", "AI_API_KEY": "", "AI_MODEL": ""}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "admin_dev.py"), "--email", ADMIN,
                             "--port", str(free_port()), "--no-browser"], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            creationflags=flags, start_new_session=os.name != "nt")
    output, found = [], threading.Event()
    link = {}

    def read():
        for line in proc.stdout:
            output.append(line)
            if "#dev=" in line and not found.is_set():
                link["url"] = line.split("Panel listo (solo esta máquina): ")[-1].strip()
                found.set()
        found.set()

    threading.Thread(target=read, daemon=True).start()
    found.wait(30)
    return proc, link.get("url"), output


def stop_panel(proc):
    # Como Ctrl+C: el script cierra el panel y borra su llave
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGINT)
        proc.wait(timeout=15)
    except Exception:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)


async def main():
    login(ADMIN)
    call("POST", "/api/feedback", {"text": XSS, "details": {"version": "v1.27.0", "view": "projects"}}, expect=201)
    # Contraseñas equivocadas, todas desde 127.0.0.1 (como si la app viera la IP del proxy)
    for _ in range(12):
        call("POST", "/api/auth/login", form={"username": "otro@test.com", "password": "equivocada"})
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_admin_panel.db"
    # Textos de IA de días pasados (paso 7: la gráfica de IA), directo en la base: sin proveedor no hay otra forma
    import sqlite3
    from datetime import datetime, timedelta, timezone
    with sqlite3.connect(db) as con:
        uid = con.execute("SELECT id FROM users WHERE email = ?", (ADMIN,)).fetchone()[0]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for days_ago, purpose, ok in [(2, "report", 1), (2, "report", 1), (1, "report", 1), (1, "costs", 0)]:
            con.execute("INSERT INTO ai_calls (user_id, created_at, purpose, model, ok, input_tokens, output_tokens)"
                        " VALUES (?, ?, ?, 'm', ?, 300, 200)",
                        (uid, (now - timedelta(days=days_ago)).isoformat(sep=" "), purpose, ok))
    keys_dirs = lambda: set(Path(tempfile.gettempdir()).glob("habit-admin-dev-*"))  # noqa: E731
    before = keys_dirs()
    proc, link, output = start_panel(db)
    check(len(keys_dirs() - before) == 1, "admin_dev.py keeps its key in a folder of its own")
    check(bool(link), f"admin_dev.py starts the panel and prints its link ({''.join(output)[-300:] if not link else 'ok'})")
    if not link:
        stop_panel(proc)
        raise AssertionError("\n".join(results))
    base = link.split("/#dev=")[0]
    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(link, wait=1.0)
        who = await b.wait_for("document.getElementById('who').textContent", lambda v: ADMIN in (v or ""))
        check(ADMIN in who and "modo de desarrollo" in who, f"it says who is in, and that it is dev mode ({who})")
        check(await b.js("location.hash") == "", "the token leaves the address bar")

        stats = await b.wait_for("[...document.querySelectorAll('#summaryStats .stat-label')].map(e => e.textContent)",
                                 lambda v: v and len(v) == 6)
        check(stats[:3] == ["Cuentas", "Nuevas", "Activas"], f"the summary shows its numbers ({stats})")

        # Paso 7: las gráficas del Resumen, con su tooltip también desde el teclado
        cards = await b.wait_for("""({cards: document.querySelectorAll('#summaryCards .card').length,
            svgs: document.querySelectorAll('#summaryCards .chart svg').length,
            bars: [...document.querySelectorAll('#summaryCards .bar-list li')].map(li => li.textContent)})""",
                                 lambda v: v and v["svgs"] >= 1)
        check(cards["cards"] == 5 and len(cards["bars"]) == 8 and "Últimas 24 h" in cards["bars"][0],
              f"the summary draws its five cards ({cards})")
        # Las cuentas de la base de prueba son de antes de la 1.27: sin fecha, esa gráfica sale vacía
        empty = await b.js("document.querySelector('#summaryCards .card .empty').textContent")
        check("Ninguna cuenta nueva" in empty, f"a chart with nothing says so ({empty})")
        # Seguridad sí tiene eventos: su última columna (hoy) enseña el tooltip al enfocarla
        await b.wait_for("document.querySelectorAll('#summaryCards .card')[4].querySelectorAll('.chart-col').length === 7")
        await b.js("document.querySelectorAll('#summaryCards .card')[4].querySelectorAll('.chart-col')[6]"
                   ".dispatchEvent(new FocusEvent('focus'))")
        tip = await b.js("(() => { const t = document.querySelectorAll('#summaryCards .card')[4].querySelector('.chart-tip'); "
                         "return t.hidden ? '' : t.textContent; })()")
        check("Contraseña equivocada al entrar" in tip, f"a column shows its tooltip on focus ({tip})")
        await b.shot("admin_summary", full=False)

        await b.js("document.querySelector('[data-tab=accounts]').click()")
        emails = await b.wait_for("[...document.querySelectorAll('#accountsTable .email')].map(e => e.textContent)", bool)
        check(emails and all("•••@" in e for e in emails), f"accounts come masked ({emails[:3]})")
        await b.js("[...document.querySelectorAll('#accountsTable .email')].find(e => e.textContent === 'y•••@test.com').click()")
        full = await b.wait_for("[...document.querySelectorAll('#accountsTable .email')].map(e => e.textContent)",
                                lambda v: ADMIN in (v or []))
        check(ADMIN in full, "tapping one shows its full email")

        await b.js("document.querySelector('[data-tab=feedback]').click()")
        text = await b.wait_for("(document.querySelector('#feedbackList .feedback-text') || {}).textContent", bool)
        st = await b.js("""({pwned: window.__pwned || null, imgs: document.querySelectorAll('#feedbackList img').length,
            scripts: document.querySelectorAll('#feedbackList script').length})""")
        check(text == XSS and st == {"pwned": None, "imgs": 0, "scripts": 0},
              f"a report with HTML shows as text and never runs ({st})")
        await b.shot("admin_feedback", full=False)

        # Paso 5: cerrarlo con una nota para la persona; la interna no le llega
        await b.js("""(() => { const form = document.querySelector('#feedbackList .feedback-editor');
            form.querySelector('select').value = 'closed';
            const [internal, forUser] = form.querySelectorAll('textarea');
            internal.value = 'Nota interna: revisar loadBoard';
            forUser.value = 'Ya quedó, gracias por avisar.';
            form.requestSubmit(); })()""")
        msg = await b.wait_for("document.getElementById('feedbackMessage').textContent", bool)
        today = __import__("datetime").date.today().isoformat()
        notices = [n for n in call("GET", f"/api/notices?today={today}", expect=200)[1]["notices"]
                   if n["kind"] == "feedback_closed"]
        check("le llegó un aviso" in msg and len(notices) == 1 and notices[0]["detail"] == "Ya quedó, gracias por avisar."
              and "loadBoard" not in str(notices), f"closing a problem tells the person, with their note only ({notices})")

        chips = await b.wait_for("[...document.querySelectorAll('#feedbackChips .chip')].map(c => c.textContent)",
                                 lambda v: v and "Cerrados1" in v)
        check(chips == ["Abiertos0", "Revisados0", "Cerrados1", "Todos1"], f"the chips count each status ({chips})")
        await b.js("document.querySelector('#feedbackChips [data-status=closed]').click()")
        shown = await b.js("document.querySelectorAll('#feedbackList .feedback').length")
        check(shown == 1, f"a chip filters the list ({shown})")

        await b.js("document.querySelector('[data-tab=accounts]').click()")
        await b.shot("admin_accounts", full=False)

        # Fase 2: la ficha de la cuenta da acceso a Maker (el navegador pasa la protección CSRF)
        await b.js("""[...document.querySelectorAll('#accountsTable tr')].find(r => r.textContent.includes('yoshi@test.com'))
            .querySelector('.manage').click()""")
        await b.wait_for("document.getElementById('accountDialog').open", bool)
        await b.js("document.querySelector('#accountModules input[data-module=maker]').click()")
        log = await b.wait_for("document.getElementById('accountLog').textContent",
                               lambda v: "Acceso a Maker dado" in (v or ""))
        maker = call("GET", "/api/auth/me", expect=200)[1]["modules"]["maker"]
        check(maker["allowed"] and "Acceso a Maker dado" in log and ADMIN in log,
              f"Gestionar gives Maker access, and the log says who ({maker}, {log[:80]})")
        # Textos de IA extra por hoy, desde la ficha
        ai_text = await b.wait_for("document.getElementById('accountAi').textContent", bool)
        check("no tiene proveedor" in ai_text, f"without a provider the sheet says so ({ai_text})")
        await b.js("""document.getElementById('aiGrantExtra').value = '3';
            document.getElementById('aiGrantForm').requestSubmit()""")
        log = await b.wait_for("document.getElementById('accountLog').textContent",
                               lambda v: "+3 textos de IA hoy (Tiempo y hábitos)" in (v or ""))
        check("+3 textos de IA hoy (Tiempo y hábitos)" in log, f"and gives 3 extra AI texts for today ({log[:120]})")
        await b.shot("admin_account_dialog", full=False)
        await b.js("document.getElementById('accountDialogClose').click()")

        # Desactivar la otra cuenta: el primer clic solo pide confirmar; el segundo la desactiva
        other_id = await b.js("accountsState.list.find(a => a.email === 'o•••@test.com').id")
        await b.js(f"openAccount({other_id})")
        await b.wait_for("document.getElementById('accountDialog').open", bool)
        await b.js("document.getElementById('accountDeactivate').click()")
        first = await b.js("""({label: document.getElementById('accountDeactivate').textContent,
            state: document.getElementById('accountState').textContent})""")
        await b.js("document.getElementById('accountDeactivate').click()")
        state = await b.wait_for("document.getElementById('accountState').textContent",
                                 lambda v: (v or "").startswith("Desactivada"))
        row = await b.js(f"[...document.querySelectorAll('#accountsTable tr')].find(r => r.textContent.includes('o•••@test.com')).textContent")
        check(first == {"label": "Confirmar: desactivar", "state": "Activa"} and state.startswith("Desactivada")
              and "Desactivada" in row, f"deactivating asks once more, then marks the account ({first}, {state})")
        await b.js("document.getElementById('accountReactivate').click()")
        state = await b.wait_for("document.getElementById('accountState').textContent", lambda v: v == "Activa")
        check(state == "Activa", "and it can be reactivated")
        await b.js("document.getElementById('accountDialogClose').click()")

        # Seguridad: los eventos, la IP y el aviso de que la app ve la IP de un proxy
        await b.js("document.querySelector('[data-tab=security]').click()")
        sec = await b.wait_for("""({warning: !document.getElementById('proxyWarning').hidden,
            heads: [...document.querySelectorAll('#securityDays th')].map(e => e.textContent),
            ip: (document.querySelector('#securityIps tbody .ip') || {}).textContent})""",
                               lambda v: bool(v and v.get("ip")))
        check(sec["warning"] and "Contraseña equivocada al entrar" in sec["heads"]
              and "Login bloqueado por el límite de intentos" in sec["heads"] and sec.get("ip") == "127.0.0.1",
              f"Seguridad shows the events and warns about the proxy IP ({sec})")
        legend = await b.wait_for("[...document.querySelectorAll('#securityChart .chart-legend li')].map(li => li.textContent)", bool)
        check("Contraseña equivocada al entrar10" in legend, f"its chart stacks the events by kind, with totals ({legend})")
        await b.shot("admin_security", full=False)

        await b.js("document.querySelector('[data-tab=ai]').click()")
        legend = await b.wait_for("[...document.querySelectorAll('#aiCalls .chart-legend li')].map(li => li.textContent)", bool)
        check(legend == ["Buenos3", "Fallidos1"], f"IA stacks good and failed texts per day ({legend})")
        await b.wait_for("document.querySelectorAll('#aiCalls .chart-col').length === 30")
        await b.shot("admin_ai", full=False)
        await b.js("(() => { const s = document.getElementById('aiPurpose'); s.value = 'costs'; s.dispatchEvent(new Event('change')); })()")
        legend = await b.wait_for("[...document.querySelectorAll('#aiCalls .chart-legend li')].map(li => li.textContent)",
                                  lambda v: v and v[0] == "Buenos0")
        check(legend == ["Buenos0", "Fallidos1"], f"the counter filter keeps only its calls ({legend})")

        # En el teléfono nada se sale de lado
        await b.viewport(390, 844, mobile=True)
        await b.js("document.querySelector('[data-tab=summary]').click()")
        await b.wait_for("document.querySelector('#summaryCards .chart svg')", bool)
        wide = await b.js("document.documentElement.scrollWidth")
        # Si algo se sale, cuál: el elemento más profundo que pasa del borde
        out = await b.js("""[...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > 390
            && ![...e.children].some(c => c.getBoundingClientRect().right > 390))
            .slice(0, 3).map(e => `${e.tagName.toLowerCase()}.${e.getAttribute('class') || ''}#${e.id} ${e.getBoundingClientRect().right.toFixed(2)} of ${innerWidth}`)""")
        check(wide <= 390, f"the summary fits a phone ({wide}px; {out})")
        await b.shot("admin_summary_phone", full=True)
        await b.viewport(1280, 900)
        # El tema oscuro sale del sistema: sus colores de las gráficas son otros (validados aparte)
        await b.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
        await b.wait_for("getComputedStyle(document.body).backgroundColor === 'rgb(20, 22, 26)'")
        await b.shot("admin_summary_dark", full=False)
        await b.send("Emulation.setEmulatedMedia", features=[])

        # La bitácora general: todo lo de arriba, el más nuevo primero, con la cuenta enmascarada
        await b.js("document.querySelector('[data-tab=log]').click()")
        rows = await b.wait_for("[...document.querySelectorAll('#logTable tbody tr')].map(r => [...r.cells].map(c => c.textContent))",
                                lambda v: v and len(v) >= 5)
        whats = [r[2] for r in rows]
        check(whats[:4] == ["Cuenta reactivada", "Cuenta desactivada", "+3 textos de IA hoy (Tiempo y hábitos)",
                            "Acceso a Maker dado"]
              and rows[0][3] == "o•••@test.com" and rows[3][3] == "y•••@test.com" and all(r[1] == ADMIN for r in rows),
              f"the Bitácora tab lists every change, newest first ({[(r[2], r[3]) for r in rows[:4]]})")
        await b.shot("admin_log", full=False)

        # Paso 6: un aviso para todas las cuentas, con vista previa, y terminarlo
        today = __import__("datetime").date.today().isoformat()

        def bell_announcements():
            return [n["title"] for n in call("GET", f"/api/notices?today={today}", expect=200)[1]["notices"]
                    if n["kind"] == "announcement"]

        await b.js("document.querySelector('[data-tab=announcements]').click()")
        await b.js("""(() => { const t = document.getElementById('announceTitle'); t.value = 'Mantenimiento programado';
            t.dispatchEvent(new Event('input'));
            const body = document.getElementById('announceBody'); body.value = 'Hoy a las 22:00, 5 min.';
            body.dispatchEvent(new Event('input')); })()""")
        preview = await b.js("document.querySelector('.announce-preview').textContent")
        await b.shot("admin_announce_preview", full=False)
        await b.js("document.getElementById('announceForm').requestSubmit()")
        listed = await b.wait_for("[...document.querySelectorAll('#announceList .announce.current strong')].map(e => e.textContent)",
                                  lambda v: v == ["Mantenimiento programado"])
        check("📢 Mantenimiento programado" in preview and "22:00" in preview and listed == ["Mantenimiento programado"]
              and bell_announcements() == ["Mantenimiento programado"],
              f"Avisos previews it, publishes it and it reaches the bell ({listed})")
        await b.js("document.querySelector('#announceList .announce.current .manage').click()")
        await b.wait_for("document.querySelectorAll('#announceList .announce.current').length === 0", bool)
        check(bell_announcements() == [], "Terminar takes it out of every bell")

        # Y un aviso solo para la otra cuenta, desde su ficha
        await b.js("document.querySelector('[data-tab=accounts]').click()")
        await b.js(f"openAccount({other_id})")
        await b.wait_for("document.getElementById('accountDialog').open", bool)
        await b.js("""document.getElementById('accountMessageTitle2').value = 'Revisa tu tablero';
            document.getElementById('accountMessageForm').requestSubmit()""")
        log = await b.wait_for("document.getElementById('accountLog').textContent",
                               lambda v: "Aviso a la cuenta: «Revisa tu tablero»" in (v or ""))
        check("Aviso a la cuenta: «Revisa tu tablero»" in log, "the sheet sends a notice to that account only")
        await b.js("document.getElementById('accountDialogClose').click()")

        # Sin token (otra pestaña, sin el enlace): acceso denegado, sin datos
        await b.js("sessionStorage.clear()")
        await b.goto(base + "/", wait=1.0)
        denied = await b.wait_for("!document.getElementById('denied').hidden", bool)
        rows = await b.js("document.querySelectorAll('#accountsTable tr').length")
        check(denied and rows == 0, f"without the token it is denied and shows nothing ({rows} rows)")
        hint = await b.js("document.getElementById('denied').textContent")
        check("admin_dev.py" in hint and "Cloudflare" not in hint, f"and on this machine it says what to do ({hint[:70]})")
    finally:
        await b.close()
        stop_panel(proc)

    log = "".join(output)
    check("MODO DE DESARROLLO" in log, "the panel log warns it runs in dev mode")
    check(keys_dirs() == before and "la llave de esta sesión se borró" in log,
          "closing it deletes the key: no token of the session works again")
    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors or "Traceback" in log:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK"))
                             + f"\nconsole errors: {errors}" + (f"\npanel log:\n{log[-2000:]}" if "Traceback" in log else ""))


def test_admin_panel():
    asyncio.run(main())
