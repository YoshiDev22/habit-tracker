"""
Teaser 0: levanta la app en local con datos de demo y saca las 6 capturas.

Reutiliza tests/ui: conftest._prepare_db (base 1.9 migrada), ui_board.seed()
(cuenta, etiquetas, tableros) y el driver CDP. Nunca toca producción ni tu .env.

    python video/teaser-0/demo.py            # capturas -> assets/ + clicks.json
    python video/teaser-0/demo.py --serve    # deja el servidor corriendo (Ctrl+C)
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
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

HABITS = [  # key, label, icon, color, días que se salta (determinista, sin azar)
    ("ejercicio", "Ejercicio", "🏃", "#e74c3c", {3, 10, 17}),
    ("lectura", "Lectura", "📚", "#3498db", {5, 12}),
    ("agua", "Agua", "💧", "#1abc9c", set()),
    ("meditar", "Meditar", "🧘", "#9b59b6", {2, 8, 9, 15, 22}),
    ("dormir", "Dormir 8 h", "😴", "#f39c12", {4, 11, 18, 25}),
]


def seed_demo():
    token, col = seed()
    # Hábitos: 5 definiciones y ~6 semanas marcadas; hoy solo "agua" (el beat 2 marca otro)
    for i, (key, label, icon, color, _) in enumerate(HABITS):
        call("POST", "/api/habits/definitions", {"key": key, "label": label, "icon": icon,
                                                  "color": color, "order": i}, expect=201)
    for back in range(0, 42):
        day = TODAY - timedelta(days=back)
        done = {k: True for k, *_, skip in HABITS if back % 29 not in skip}
        if back == 0:
            done = {"agua": True}
        call("POST", "/api/habits", {"date": day.isoformat(), "habits": done}, expect=200)

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
    targets = [(tesis["id"], tasks["Redactar introducción"]["id"]),
               (tesis["id"], tasks["Buscar bibliografía"]["id"]),
               (ht["Revisión de idea para cambiar a kanban"]["project_id"], ht["Revisión de idea para cambiar a kanban"]["id"]),
               (ht["Corrección de Pomodoros"]["project_id"], ht["Corrección de Pomodoros"]["id"])]
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
    _, h = call("GET", f"/api/habits?today={TODAY.isoformat()}", expect=200)
    print("streak:", h.get("streak"), "shields:", h.get("streak_shields"))
    return token, h.get("streak")


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


RECT = """((el) => { if (!el) return null; const r = el.getBoundingClientRect();
  return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
          w: Math.round(r.width), h: Math.round(r.height)}; })(%s)"""


async def capture(token, streak):
    ASSETS.mkdir(parents=True, exist_ok=True)
    b = Browser()
    await b.start()
    clicks = {}

    async def shot(name, selector_js, label):
        await asyncio.sleep(0.4)
        path = await b.shot(name, full=False)
        shutil.copy(path, ASSETS / f"{name}.png")
        clicks[name] = {"label": label, **(await b.js(RECT % selector_js) or {})}

    try:
        await b.viewport(W, H)
        # Same 1280x800 CSS viewport, rendered at 2x: the montage zooms up to ~2.5x
        await b.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=2, mobile=False)
        await b.goto(api.BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});"
                   f"localStorage.setItem('theme', 'light'); localStorage.removeItem('projects_view');"
                   f"localStorage.setItem('missed_day_asked', 'x')")
        await b.goto(api.BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.wait_for("document.getElementById('streakCount').textContent", lambda v: v not in ("0", None))

        # 800 px no alcanza para calendario + racha: bajar lo justo para ver la racha
        await b.js("window.scrollTo(0, document.getElementById('streakCount').closest('div').getBoundingClientRect().bottom + scrollY - 770)")
        await shot("01_calendar", "document.getElementById('streakCount')", "racha")

        today_cell = "document.querySelector('.day-cell.today')"
        await b.js(f"{today_cell}.click()")
        await b.wait_for("!document.getElementById('habitPopover').classList.contains('hidden')")
        await b.js("window.scrollBy(0, document.getElementById('habitPopover').getBoundingClientRect().bottom - 770)")
        await shot("02_day_panel", "document.querySelector('#habitsList .habit-btn:not(.completed)')",
                   "hábito a marcar")
        clicks["02_day_panel"]["cell"] = await b.js(RECT % today_cell)

        await b.js("document.body.click()")
        await b.js("document.getElementById('tabProjects').click(); window.scrollTo(0, 0)")
        await b.wait_for("document.querySelectorAll('.board-card').length", lambda v: v and v >= 6)
        await asyncio.sleep(0.8)
        await shot("03_board", "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Redactar'))",
                   "tarjeta en Haciendo")
        clicks["03_board"]["list_toggle"] = await b.js(RECT % "document.querySelector('[data-projects-view=\"list\"]')")

        await b.js("document.querySelector('[data-projects-view=\"list\"]').click()")
        await b.wait_for("document.querySelectorAll('.project-card').length", lambda v: v and v >= 2)
        await asyncio.sleep(0.8)
        await shot("04_list", "document.querySelector('.project-card')", "proyecto")

        await b.js("document.querySelector('[data-projects-view=\"board\"]').click()")
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(0.5)
        await b.js("document.querySelector('[data-range=\"month\"]').click()")
        await b.wait_for("document.querySelectorAll('#reportsBody svg').length", lambda v: v and v >= 1)
        await asyncio.sleep(1.0)
        await shot("05_reports", "document.querySelector('#reportsBody').firstElementChild", "resumen del mes")

        await b.js("document.getElementById('reportsExport').focus()")
        await shot("06_export", "document.getElementById('reportsExport')", "Exportar CSV")
        errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
        if errors:
            print("console errors:", *errors, sep="\n  ")
    finally:
        await b.close()
    first = TODAY.replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    clicks["meta"] = {"viewport": [W, H], "scale": 2, "streak": streak,
                      "csv_name": f"habit-tracker-tiempo_{first}_{last}.csv"}
    (HERE / "clicks.json").write_text(json.dumps(clicks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(clicks, ensure_ascii=False, indent=1))


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
