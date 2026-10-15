"""Logros: encender el módulo, escribir uno con fecha de solo mes y evidencias, la
vitrina, el detalle y el botón SOS, en un teléfono y en los dos temas."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import api
from api import login, wait_api
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"

# Una imagen y un PDF hechos en la página, puestos en el <input type="file">
ATTACH = """(async () => {
    const canvas = document.createElement('canvas');
    canvas.width = 300; canvas.height = 200;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#3b82f6'; ctx.fillRect(0, 0, 300, 200);
    const png = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    const dt = new DataTransfer();
    dt.items.add(new File([png], 'diploma.png', {type: 'image/png'}));
    dt.items.add(new File(['%PDF-1.4\\n%%EOF\\n'], 'constancia.pdf', {type: 'application/pdf'}));
    document.getElementById('achFiles').files = dt.files;
    return document.getElementById('achFiles').files.length;
})()"""


async def main():
    login("yoshi@test.com")
    _, projects = api.call("GET", "/api/projects", expect=200)
    ht = next(p for p in projects["projects"] if p["name"] == "Habit Tracker")
    # 4 h más: con lo de la base de prueba, Habit Tracker pasa de 10 h (un hito)
    end = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    start = end - timedelta(hours=4)
    api.call("POST", "/api/pomodoro", {
        "project_id": ht["id"], "task_id": None, "session_date": datetime.now().date().isoformat(),
        "started_at": start.isoformat(), "ended_at": end.isoformat(), "duration_seconds": 4 * 3600,
        "planned_seconds": 4 * 3600, "mode": "focus", "was_completed": True, "source": "manual"}, expect=201)
    token = api.TOKEN
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        check(await b.js("document.getElementById('tabAchievements').hidden"), "off by default: no Logros tab")
        await b.js("openSettings('modules')")
        await b.wait_for("!document.getElementById('habitsSetupModal').classList.contains('hidden')")
        await b.js("document.getElementById('moduleAchievements').click()")
        me = await wait_api("/api/auth/me", lambda body: body["modules"]["achievements"]["enabled"])
        check(me["modules"]["achievements"]["enabled"], "turning it on is saved")
        await b.js("document.getElementById('settingsClose').click()")
        await b.wait_for("!document.getElementById('tabAchievements').hidden")
        await b.js("document.getElementById('tabAchievements').click()")
        await b.wait_for("document.querySelectorAll('#achBody .ach-item').length >= 1")
        titles = await b.js("[...document.querySelectorAll('#achBody .ach-item-title')].map(n => n.textContent)")
        check("10 h de enfoque en Habit Tracker" in titles, f"the 10 h milestone shows up by itself ({titles})")

        # Uno nuevo: solo mes y año, una colección nueva y dos evidencias
        await b.js("document.getElementById('achAddBtn').click()")
        await b.wait_for("!document.getElementById('achievementModal').classList.contains('hidden')")
        await b.js("""(() => {
            document.getElementById('achTitle').value = 'Constancia de ponente';
            document.querySelector('.ach-precision [data-precision="month"]').click();
            document.getElementById('achMonth').value = '06';
            document.getElementById('achYear').value = '2019';
            const col = document.getElementById('achCollection');
            col.value = '__new__'; col.dispatchEvent(new Event('change'));
            document.getElementById('achNewCollection').value = 'Impartí clases';
        })()""")
        check(await b.js(ATTACH) == 2, "two files attached")
        await b.shot("achievements_form_mobile", full=False)
        await b.js("document.getElementById('achSaveBtn').click()")
        await b.wait_for("document.getElementById('achievementModal').classList.contains('hidden')", timeout=12)
        _, data = api.call("GET", "/api/achievements", expect=200)
        mine = next((a for a in data["achievements"] if a["title"] == "Constancia de ponente"), None)
        check(mine is not None and mine["date"] == "2019-06" and mine["date_precision"] == "month",
              f"saved with month precision ({mine and mine['date']})")
        check(mine is not None and sorted(f["mime"] for f in mine["files"]) == ["application/pdf", "image/png"],
              "both files uploaded")
        check([c["name"] for c in data["collections"]] == ["Impartí clases"], "the new collection was created")
        await b.wait_for("[...document.querySelectorAll('#achBody .ach-item')].some(r => r.textContent.includes('junio de 2019') && r.querySelector('img'))")
        row = await b.js("[...document.querySelectorAll('#achBody .ach-item')].find(r => r.textContent.includes('Constancia')).textContent")
        check("junio de 2019" in row, f"the timeline says the month, not a made-up day ({row})")
        check(await b.js("!!document.querySelector('#achBody .ach-item-thumb img[src^=\"blob:\"]')"),
              "the thumbnail is loaded with the token (blob URL)")
        wide = await b.js("document.documentElement.scrollWidth")
        check(wide <= 390, f"no horizontal overflow on a phone ({wide}px)")
        await b.shot("achievements_timeline_mobile", full=True)

        # Vitrina: la colección agrupa
        await b.js("document.querySelector('[data-ach-view=\"showcase\"]').click()")
        await b.wait_for("document.querySelectorAll('.ach-collection-title').length >= 1")
        heading = await b.js("document.querySelector('.ach-collection-title').textContent")
        check(heading == "Impartí clases · 1 pieza", f"the showcase groups by collection ({heading})")
        await b.shot("achievements_showcase_mobile", full=True)

        # Detalle: abrir la imagen dentro del modal
        await b.js("document.querySelector('.ach-tile').click()")
        await b.wait_for("!document.getElementById('achDetailModal').classList.contains('hidden')")
        await b.wait_for("document.querySelectorAll('#achDetailBody .ach-files .ach-tile').length === 2")
        await b.js("[...document.querySelectorAll('#achDetailBody .ach-files .ach-tile')].find(t => t.textContent.includes('diploma')).click()")
        await b.wait_for("!document.getElementById('achViewer').hidden && document.getElementById('achViewerImg').src.startsWith('blob:')")
        check(await b.js("document.getElementById('achViewerImg').naturalWidth") == 300, "the full image opens in the detail")
        await b.shot("achievements_detail_mobile", full=False)
        await b.js("document.querySelector('#achDetailModal .modal-close').click()")

        # SOS
        for i in range(3):
            api.call("POST", "/api/achievements", {"title": f"Anécdota {i}", "date": "2021-0" + str(i + 1),
                                                   "kind": "anecdote", "what_it_shows": "Que puedo con lo difícil"},
                     expect=201)
        await b.js("document.getElementById('achSosBtn').click()")
        await b.wait_for("document.querySelectorAll('#sosAchievements .sos-card').length === 3")
        first = await b.js("[...document.querySelectorAll('#sosAchievements .ach-item-title')].map(n => n.textContent)")
        fact = await b.js("document.getElementById('sosFact').textContent")
        action = await b.js("document.getElementById('sosAction').textContent")
        check(bool(fact) and "semana" not in fact, f"a cumulative fact ({fact})")
        check(bool(action), f"a small action ({action})")
        await b.shot("achievements_sos_mobile", full=True)
        await b.js("document.getElementById('sosMore').click()")
        await b.wait_for(f"(t => t.length && t.join() !== {json.dumps(','.join(first))})([...document.querySelectorAll('#sosAchievements .ach-item-title')].map(n => n.textContent))")
        second = await b.js("[...document.querySelectorAll('#sosAchievements .ach-item-title')].map(n => n.textContent)")
        check(not set(first) & set(second), f"«Otro» does not repeat in the same opening ({first} / {second})")
        await b.js("document.getElementById('sosNote').value = 'Hoy me cuesta, pero ya vi esto';")
        await b.js("document.querySelector('#sosNoteForm button[type=submit]').click()")
        notes = await wait_api("/api/achievements/sos/notes", lambda body: len(body) == 1)
        check(len(notes) == 1 and notes[0]["note_date"] == datetime.now().date().isoformat(),
              "the note is saved with today's local date")
        await b.js("document.documentElement.setAttribute('data-theme', 'dark')")
        await asyncio.sleep(0.2)
        await b.shot("achievements_sos_dark", full=True)
        await b.js("document.querySelector('#sosModal .modal-close').click()")
        check(await b.js("document.getElementById('sosModal').classList.contains('hidden')"), "SOS closes")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_achievements():
    asyncio.run(main())
