"""
Teaser 0.1 (v1.16.0): levanta la app en local con datos de demo y saca las 10 capturas.

Reutiliza tests/ui: conftest._prepare_db (base 1.9 migrada), ui_board.seed()
(cuenta, etiquetas, tableros) y el driver CDP. Nunca toca producción ni tu .env.
Todas las capturas son de la app real: nada se dibuja encima.

    python video/teaser-0.1/demo.py            # capturas -> assets/ + clicks.json
    python video/teaser-0.1/demo.py --serve    # deja el servidor corriendo (Ctrl+C)
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tests" / "ui"))

# Linux container as root: the wrapper adds --no-sandbox (cdp.py does not).
if not os.environ.get("HABIT_UI_BROWSER") and os.name == "posix" and os.path.exists("/opt/pw-browsers/chromium"):
    os.environ["HABIT_UI_BROWSER"] = str(HERE / "chromium.sh")

import conftest  # noqa: E402  (fija HABIT_UI_BASE / HABIT_UI_TMP antes de importar api)
import api  # noqa: E402
from api import call  # noqa: E402
from cdp import Browser  # noqa: E402
from ui_board import seed, CLOSE_WELCOME  # noqa: E402

ASSETS = HERE / "assets"
W, H = 1280, 800
TODAY = date.today()
DISPLAY_NAME = "Santi"
REST_DAYS = [5, 6]                 # Sáb, Dom (0 = lunes, como en la app)
PAUSE = (TODAY + timedelta(days=1), TODAY + timedelta(days=6))   # 6 días, empieza mañana
MISSED_BACK = 4                    # un día laborable sin nada: gasta un escudo
OLD_RUN = range(130, 56, -1)       # racha vieja y larga -> el récord
GAP = range(56, 46, -1)            # sin nada: gasta los 2 escudos y corta

HABITS = [  # key, label, icon, color, "se lo salta cuando back % 23 está aquí"
    ("ejercicio", "Ejercicio", "🏃", "#e74c3c", {3, 10, 17}),
    ("lectura", "Lectura", "📚", "#3498db", {5, 12}),
    ("agua", "Agua", "💧", "#1abc9c", set()),
    ("meditar", "Meditar", "🧘", "#9b59b6", {2, 8, 15, 22}),
]
TODAY_DONE = {"ejercicio": True, "lectura": True, "agua": True}   # "3 de 4 hoy"; falta meditar


def seed_demo():
    token, col = seed()
    # seed() deja "Yoshio": el teaser usa otro nombre visible
    call("PATCH", "/api/auth/me", {"display_name": DISPLAY_NAME, "rest_days": REST_DAYS}, expect=200)

    for i, (key, label, icon, color, _) in enumerate(HABITS):
        call("POST", "/api/habits/definitions", {"key": key, "label": label, "icon": icon,
                                                  "color": color, "order": i}, expect=201)
    for back in range(130, -1, -1):
        day = TODAY - timedelta(days=back)
        if back == 0:
            done = TODAY_DONE
        elif day.weekday() in REST_DAYS or back in GAP or back == MISSED_BACK:
            continue
        else:
            done = {k: True for k, *_, skip in HABITS if back % 23 not in skip}
        call("POST", "/api/habits", {"date": day.isoformat(), "habits": done}, expect=200)
    call("POST", f"/api/habits/pauses?today={TODAY}", {"start_date": PAUSE[0].isoformat(),
                                                       "end_date": PAUSE[1].isoformat()}, expect=201)

    # Segundo proyecto con tarjetas en las tres columnas de "Mi tablero"
    _, tesis = call("POST", "/api/projects", {"name": "Tesis", "color": "#e67e22", "icon": "🎓"}, expect=201)
    tasks = {}
    for title, column in [("Diseñar encuesta", "Por hacer"), ("Revisar con asesor", "Por hacer"),
                          ("Redactar introducción", "Haciendo"), ("Buscar bibliografía", "Hecho")]:
        _, t = call("POST", "/api/tasks", {"title": title, "project_id": tesis["id"],
                                           "column_id": col[column]}, expect=201)
        tasks[title] = t
    _, tl = call("GET", "/api/tasks", expect=200)
    ht = {t["title"]: t for t in tl["tasks"]}

    # Tiempo: 1-3 sesiones por día en el último mes, horas variadas (mapa por hora)
    kanban, pomos = ht["Revisión de idea para cambiar a kanban"], ht["Corrección de Pomodoros"]
    targets = [(tesis["id"], tasks["Redactar introducción"]["id"]),
               (tesis["id"], tasks["Buscar bibliografía"]["id"]),
               (kanban["project_id"], kanban["id"]), (pomos["project_id"], pomos["id"])]
    utc_offset = datetime.now().astimezone().utcoffset()
    for back in range(0, 30):
        day = TODAY - timedelta(days=back)
        for n in range(1 + (back * 7) % 3):
            hour = 8 + (back * 5 + n * 4) % 12
            mins = 25 + ((back + n) * 13) % 70
            start_local = datetime(day.year, day.month, day.day, hour, (n * 17) % 60)
            if back == 0 and start_local + timedelta(minutes=mins) > datetime.now():
                continue
            start = start_local - utc_offset
            pid, tid = targets[(back + n) % len(targets)]
            call("POST", "/api/pomodoro", {
                "project_id": pid, "task_id": tid, "session_date": day.isoformat(),
                "started_at": start.isoformat(), "ended_at": (start + timedelta(minutes=mins)).isoformat(),
                "duration_seconds": mins * 60, "planned_seconds": 1500, "mode": "focus",
                "was_completed": True, "source": "manual"}, expect=201)
    _, st = call("GET", f"/api/habits/streak?today={TODAY}", expect=200)
    print("streak:", json.dumps(st, ensure_ascii=False)[:400])
    return token, st


def start_server():
    db = conftest.TMP / "demo.db"
    conftest._prepare_db(db)
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SECRET_KEY": "demo-secret-key-not-for-production", "PYTHONIOENCODING": "utf-8"}
    log = open(conftest.TMP / "demo.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(conftest.PORT)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            urllib.request.urlopen(api.BASE + "/api/health", timeout=1)
            return proc
        except Exception:
            time.sleep(0.2)
    raise RuntimeError((conftest.TMP / "demo.log").read_text(encoding="utf-8"))


# Center and size of an element, in viewport CSS px (the screenshot's coordinates)
RECT = """((el) => { if (!el) return null; const r = el.getBoundingClientRect();
  return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
          w: Math.round(r.width), h: Math.round(r.height)}; })(%s)"""
CELL = "document.querySelector('.day-cell[data-date=\"%s\"]')"
SCROLL_TO = "window.scrollTo(0, 0); window.scrollTo(0, (%s).getBoundingClientRect().%s + scrollY - %d)"


def weekend_keys():
    """The Sáb and Dom columns of the current month (rest days), for the weekend beat."""
    first = TODAY.replace(day=1)
    days = [first + timedelta(days=i) for i in range(31) if (first + timedelta(days=i)).month == first.month
            and first + timedelta(days=i) < TODAY]
    sats = [d for d in days if d.weekday() == 5]
    suns = [d for d in days if d.weekday() == 6]
    return {"sat_first": CELL % sats[0], "sat_last": CELL % sats[-1],
            "sun_first": CELL % suns[0], "sun_last": CELL % suns[-1],
            "head_sat": "[...document.querySelectorAll('.weekdays div')].find(d => d.textContent === 'Sáb')",
            "head_sun": "[...document.querySelectorAll('.weekdays div')].find(d => d.textContent === 'Dom')"}


async def capture(token, streak):
    ASSETS.mkdir(parents=True, exist_ok=True)
    b = Browser()
    await b.start()
    clicks = {}
    private = []   # "Yoshio" or an e-mail visible in any capture

    async def shot(name, key_js, label, **extra):
        await asyncio.sleep(0.5)
        path = await b.shot(name, full=False)
        shutil.copy(path, ASSETS / f"{name}.png")
        clicks[name] = {"label": label, **(await b.js(RECT % key_js) or {})}
        for k, js in extra.items():
            clicks[name][k] = await b.js(RECT % js)
        leak = await b.js("""(() => { const t = document.body.innerText;
            return /Yoshio/.test(t) || /[\\w.]+@[\\w.]+\\.\\w+/.test(t); })()""")
        if leak:
            private.append(name)

    try:
        await b.viewport(W, H)
        # Same 1280x800 CSS viewport, rendered at 2x: the montage zooms up to ~2.5x
        await b.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=2, mobile=False)
        await b.goto(api.BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});"
                   f"localStorage.setItem('theme', 'light'); localStorage.removeItem('projects_view');")
        await b.goto(api.BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.wait_for("document.getElementById('streakCount').textContent", lambda v: v not in ("0", None))
        await b.wait_for("document.querySelectorAll('#habitLegend > *').length", lambda v: v and v >= 4)

        # 1. Franja de racha arriba y leyenda debajo: bajar lo justo para que quepan las dos
        await b.js(SCROLL_TO % ("document.getElementById('legendBlock')", "bottom", 785))
        await shot("01_calendar", "document.getElementById('streakStrip')", "franja de racha",
                   legend="document.getElementById('legendBlock')",
                   shields="document.getElementById('streakShields')",
                   **weekend_keys())

        # 2. Panel de hoy ANTES: "3 de 4 hoy", Meditar con el círculo vacío
        today = CELL % TODAY.isoformat()
        await b.js(f"{today}.click()")
        await b.wait_for("!document.getElementById('habitPopover').classList.contains('hidden')")
        await b.js("window.scrollBy(0, document.getElementById('habitPopover').getBoundingClientRect().bottom - 780)")
        scroll_y = await b.js("scrollY")
        pending = "[...document.querySelectorAll('#habitsList .habit-btn')].find(x => x.dataset.habit === 'meditar')"
        await shot("02_day_before", pending, "Meditar (vacío)",
                   count="document.getElementById('popoverCount')", cell=today)
        count_before = await b.js("document.getElementById('popoverCount').textContent")

        # 3. Clic de verdad en Meditar. La app cierra el panel al registrar: se vuelve a
        #    abrir con otro clic real en hoy, en el mismo scroll, para cortar 2 -> 3.
        await b.js(f"{pending}.click()")
        await b.wait_for("document.getElementById('streakCount').textContent", lambda v: v is not None)
        await asyncio.sleep(1.2)
        await b.js(f"window.scrollTo(0, {scroll_y}); {today}.click()")
        await b.wait_for("document.getElementById('popoverCount').textContent", lambda v: v and v.startswith("4 de 4"))
        await shot("03_day_after", pending, "Meditar (relleno)",
                   count="document.getElementById('popoverCount')", cell=today)
        count_after = await b.js("document.getElementById('popoverCount').textContent")
        await b.js("document.body.click()")

        # 4. ⚙️ Configuración de hábitos: lista con emoji/color y días de descanso
        await b.js("window.scrollTo(0, 0); document.getElementById('settingsBtn').click()")
        await b.wait_for("document.querySelectorAll('#habitsOptions > *').length", lambda v: v and v >= 4)
        await b.wait_for("document.querySelectorAll('#pauseList li').length", lambda v: v and v >= 1)
        await asyncio.sleep(0.6)
        scroller = "document.querySelector('#habitsSetupModal .setup-scroll')"
        await b.js(f"{scroller}.scrollTop = 0")
        await shot("04_settings", "document.getElementById('habitsOptions')", "tus hábitos",
                   first_color="document.querySelector('#habitsOptions input[type=color]')",
                   last_row="document.querySelector('#habitsOptions').lastElementChild",
                   rest="document.getElementById('restDaysOptions')",
                   modal="document.querySelector('#habitsSetupModal .modal-content')")

        # 5. Vacaciones: al fondo del mismo modal, con la pausa programada
        await b.js(f"{scroller}.scrollTop = {scroller}.scrollHeight")
        await shot("05_vacations", "document.getElementById('pauseList')", "pausa programada",
                   rest="document.getElementById('restDaysOptions')",
                   section="document.querySelector('.pause-section')")
        await b.js("document.querySelector('#habitsSetupModal .modal-overlay').click()")
        await asyncio.sleep(0.4)
        await b.js(CLOSE_WELCOME)

        # 6. Mes con la pausa (hoy está a fin de mes: los días rayados caen en el siguiente)
        month_of_pause = PAUSE[1].month
        if month_of_pause != TODAY.month:
            await b.js("document.getElementById('nextMonth').click()")
        await b.wait_for("document.querySelectorAll('.day-cell.paused').length", lambda v: v and v >= 3)
        await asyncio.sleep(0.6)
        await b.js(SCROLL_TO % ("document.querySelector('.calendar')", "bottom", 790))
        sat = await b.js("[...document.querySelectorAll('.day-cell.rest-day:not(.paused)')].map(c => c.dataset.date)")
        paused = await b.js("[...document.querySelectorAll('.day-cell.paused')].map(c => c.dataset.date)")
        weekend = next(d for d in sat if date.fromisoformat(d).weekday() == 5)
        mid_pause = paused[len(paused) // 2]
        await shot("06_rest_vacation", CELL % mid_pause, "días de vacaciones",
                   weekend_sat=CELL % weekend,
                   weekend_sun=CELL % (date.fromisoformat(weekend) + timedelta(days=1)).isoformat(),
                   pause_first=CELL % paused[0], pause_last=CELL % paused[-1])
        await b.js("document.getElementById('prevMonth').click(); window.scrollTo(0, 0)")

        # 7-8. Tablero y Lista
        await b.js("document.getElementById('tabProjects').click(); window.scrollTo(0, 0)")
        await b.wait_for("document.querySelectorAll('.board-card').length", lambda v: v and v >= 6)
        await asyncio.sleep(0.8)
        await shot("07_board", "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Redactar'))",
                   "tarjeta en Haciendo", list_toggle="document.querySelector('[data-projects-view=\"list\"]')")
        await b.js("document.querySelector('[data-projects-view=\"list\"]').click()")
        await b.wait_for("document.querySelectorAll('.project-card').length", lambda v: v and v >= 2)
        await asyncio.sleep(0.8)
        await shot("08_list", "document.querySelector('.project-card')", "proyecto")

        # 9-10. Reportes del mes y Exportar CSV
        await b.js("document.querySelector('[data-projects-view=\"board\"]').click()")
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(0.5)
        await b.js("document.querySelector('[data-range=\"month\"]').click()")
        await b.wait_for("document.querySelectorAll('#reportsBody svg').length", lambda v: v and v >= 1)
        await asyncio.sleep(1.0)
        await shot("09_reports", "document.querySelector('#reportsBody').firstElementChild", "resumen del mes",
                   habits="[...document.querySelectorAll('#reportsBody > *')].find(e => /HÁBITOS|Hábitos/.test(e.innerText))")
        await b.js("document.getElementById('reportsExport').focus()")
        await shot("10_export", "document.getElementById('reportsExport')", "Exportar CSV")

        errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
        if errors:
            print("console errors:", *errors, sep="\n  ")
    finally:
        await b.close()

    first = TODAY.replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    clicks["meta"] = {
        "viewport": [W, H], "scale": 2, "display_name": DISPLAY_NAME,
        "streak": streak.get("streak"), "best": streak.get("best_streak"),
        "count_before": count_before, "count_after": count_after,
        "pause": [PAUSE[0].isoformat(), PAUSE[1].isoformat()],
        "csv_name": f"habit-tracker-tiempo_{first}_{last}.csv",
    }
    (HERE / "clicks.json").write_text(json.dumps(clicks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(clicks["meta"], ensure_ascii=False))
    if private:
        raise SystemExit(f"'Yoshio' or an e-mail is visible in: {private}")


def main():
    proc = start_server()
    try:
        token, streak = seed_demo()
        if "--serve" in sys.argv:
            print(f"{api.BASE}  (yoshi@test.com / {api.PASSWORD})  Ctrl+C para salir")
            proc.wait()
        else:
            asyncio.run(capture(token, streak))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(conftest.TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
