"""El centro de avisos (1.26): el día sin anotar (con su ventana, que se queda) y
el reporte automático listo, de punta a punta, con el círculo rojo."""
import asyncio
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import api
from api import login
from cdp import Browser

BASE = api.BASE
ROOT = Path(__file__).resolve().parents[2]
results = []
COUNT = "(document.getElementById('bellCount').hidden ? 0 : Number(document.getElementById('bellCount').textContent))"
MODAL = "!document.getElementById('{}').classList.contains('hidden')"


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def auto_report(email, monday):
    """Un reporte del timer (trigger auto) en la base de esta prueba."""
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_notice_center.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}", "PYTHONIOENCODING": "utf-8",
           "SECRET_KEY": "test-secret-key-not-for-production", "HABIT_HOLIDAYS_OFFLINE": "1",
           "AI_BASE_URL": "", "AI_MODEL": ""}
    code = ("from datetime import date; from sqlmodel import Session, select; from backend.database import engine;"
            "from backend.models import User; from backend.reports import generate_report;"
            f"s = Session(engine); u = s.exec(select(User).where(User.email == '{email}')).one();"
            f"print(generate_report(s, u, 'week', date.fromisoformat('{monday}'), date.today(), trigger='auto').id)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return int(out.stdout.strip().splitlines()[-1])


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    api.call("POST", "/api/habits/definitions", {"key": "leer", "label": "Leer"}, expect=201)
    for i in (2, 3):
        api.call("PATCH", f"/api/habits/day/{today - timedelta(days=i)}", {"habit_key": "leer", "done": True}, expect=200)
    _, projects = api.call("GET", "/api/projects", expect=200)
    project = projects["projects"][0]
    monday = today - timedelta(days=today.weekday() + 7)
    start = f"{monday}T15:00:00"
    api.call("POST", "/api/pomodoro", {"project_id": project["id"], "task_id": None, "session_date": monday.isoformat(),
                                        "started_at": start, "ended_at": f"{monday}T16:00:00", "duration_seconds": 3600,
                                        "planned_seconds": 0, "mode": "focus", "was_completed": True, "source": "stopwatch"},
             expect=201)
    report_id = auto_report("yoshi@test.com", monday.isoformat())

    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
        await b.goto(BASE + "/", wait=2.5)
        # La ventana de ayer se queda; cerrarla con la × deja el aviso pendiente
        asked = await b.wait_for(MODAL.format("missedDayModal"), timeout=10)
        check(asked, "the '¿Olvidaste anotar ayer?' window still shows")
        await b.js("document.querySelector('#missedDayModal .modal-close').click()")
        two = await b.wait_for(f"{COUNT} === 2", timeout=10)
        check(two, "the bell counts the missed day and the unread report (2)")

        await b.js("document.getElementById('bellBtn').click()")
        await b.wait_for("document.querySelectorAll('#noticesList .notice-item').length >= 2")
        st = await b.js("""({groups: [...document.querySelectorAll('#noticesList .notice-group')].map(g => g.textContent),
            text: document.getElementById('noticesList').textContent})""")
        check(st["groups"][:2] == ["Pendientes", "Avisos"] and "Día sin anotar" in st["text"]
              and "Tu reporte semanal de tiempo está listo" in st["text"], f"pending first, then the info ({st['groups']})")
        one = await b.wait_for(f"{COUNT} === 1")
        check(one, "opening the bell reads the info notice: only the pending one counts")
        await b.shot("notice_center", full=False)

        # Ver el reporte desde el aviso
        await b.js("document.querySelector('#noticesList .notice-info [data-action=open]').click()")
        await b.wait_for("document.getElementById('savedReportTitle').textContent === 'Reporte semanal de tiempo'", timeout=10)
        check(await b.js("savedState.current && savedState.current.id") == report_id, "'Ver reporte' opens that report")
        await b.js("document.getElementById('savedReportClose').click()")

        # Anotar el día desde el aviso: abre ese día, se marca, y el aviso pasa a hecho
        await b.js("document.getElementById('bellBtn').click()")
        await b.wait_for("document.querySelector('#noticesList .notice-pending [data-action=day]')")
        await b.js("document.querySelector('#noticesList .notice-pending [data-action=day]').click()")
        opened = await b.wait_for("!document.getElementById('habitPopover').classList.contains('hidden')")
        await asyncio.sleep(0.3)   # que un cierre tardío (el bug de antes) tuviera tiempo de pasar
        shown = await b.js("document.getElementById('popoverDate').textContent")
        still = await b.js("!document.getElementById('habitPopover').classList.contains('hidden')")
        day_num = str(int(yesterday[8:]))
        check(opened and still and day_num in shown and await b.js("currentViewId") == "calendar",
              f"'Anotar' opens that day in the calendar and its panel stays open ({shown}, open={still})")
        await b.js("document.querySelector('#habitsList .habit-btn[data-habit=leer]').click()")
        cleared = await b.wait_for(f"{COUNT} === 0", timeout=10)
        await b.js("document.getElementById('bellBtn').click()")
        moved = await b.wait_for("document.getElementById('noticesList').textContent.includes('Día anotado')")
        check(cleared and moved, "marking it moves the notice to Hechos and the bell is clear")
        await b.js("document.getElementById('noticesClose').click()")

        # Un anuncio para todas las cuentas (scripts/announce.py): con 📢, sin botón, y cuenta en el círculo
        db = Path(os.environ["HABIT_UI_TMP"]) / "test_notice_center.db"
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "announce.py"), "--title", "Mantenimiento programado",
                              "--body", "La app se reinicia hoy a las 22:00 (unos 5 minutos).", "--hours", "2"],
                             cwd=ROOT, env={**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}"},
                             capture_output=True, text=True)
        check(out.returncode == 0, f"announce.py publishes ({out.stdout.strip()} {out.stderr.strip()})")
        await b.js("refreshNotices()")
        check(await b.wait_for(f"{COUNT} === 1", timeout=10), "the announcement counts in the bell (1)")
        await b.js("document.getElementById('bellBtn').click()")
        await b.wait_for("document.getElementById('noticesList').textContent.includes('Mantenimiento programado')")
        st = await b.js("""(() => { const item = [...document.querySelectorAll('#noticesList .notice-item')]
            .find(i => i.textContent.includes('Mantenimiento')); return {text: item.textContent,
            buttons: item.querySelectorAll('button').length}; })()""")
        check("📢" in st["text"] and "22:00" in st["text"] and st["buttons"] == 0,
              f"the announcement shows with 📢, its text and no button ({st})")
        await b.shot("notice_announcement", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_notice_center():
    asyncio.run(main())
