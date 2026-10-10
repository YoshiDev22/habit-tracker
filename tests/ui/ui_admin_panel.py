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
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_admin_panel.db"
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

        # Sin token (otra pestaña, sin el enlace): acceso denegado, sin datos
        await b.js("sessionStorage.clear()")
        await b.goto(base + "/", wait=1.0)
        denied = await b.wait_for("!document.getElementById('denied').hidden", bool)
        rows = await b.js("document.querySelectorAll('#accountsTable tr').length")
        check(denied and rows == 0, f"without the token it is denied and shows nothing ({rows} rows)")
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
