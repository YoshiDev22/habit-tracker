import asyncio
import json
import sys

import api
from api import call, login
from cdp import Browser

BASE = api.BASE


def seed():
    login("yoshi@test.com")
    call("PATCH", "/api/auth/me", {"display_name": "Yoshio"})
    _, bl = call("GET", "/api/boards", expect=200)
    board = bl["boards"][0]
    col = {c["name"]: c["id"] for c in board["columns"]}
    _, tl = call("GET", "/api/tasks", expect=200)
    by = {t["title"]: t for t in tl["tasks"]}
    _, doc = call("POST", "/api/tags", {"name": "documentación", "color": "#8e44ad"}, expect=201)
    _, adm = call("POST", "/api/tags", {"name": "administrativa", "color": "#e67e22"}, expect=201)
    kanban = by["Revisión de idea para cambiar a kanban"]
    call("PATCH", f"/api/tasks/{kanban['id']}", {"column_id": col["Haciendo"], "tag_ids": [doc["id"]]}, expect=200)
    call("PATCH", f"/api/tasks/{by['Corrección de Pomodoros']['id']}", {"tag_ids": [doc["id"], adm["id"]]}, expect=200)
    for text in ("Leer artículos de Trello", "Definir columnas", "Diseñar tarjetas"):
        _, item = call("POST", f"/api/tasks/{kanban['id']}/checklist", {"text": text}, expect=201)
    call("PATCH", f"/api/tasks/{kanban['id']}/checklist/{item['id'] - 2}", {"is_done": True}, expect=200)
    call("POST", f"/api/tasks/{kanban['id']}/comments", {"body": "Investigar GTD y Personal Kanban"}, expect=201)
    call("POST", "/api/tasks", {"title": "Idea suelta sin proyecto"}, expect=201)
    _, school = call("POST", "/api/boards", {"name": "Escuela"}, expect=201)
    call("POST", "/api/tasks", {"title": "Capítulo 3: funciones", "board_id": school["id"]}, expect=201)
    return api.TOKEN, col


CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.0)

        state = await b.js("""({
            wide: document.body.classList.contains('board-wide'),
            columns: [...document.querySelectorAll('.board-column')].map(c => c.querySelector('.board-column-name').textContent + ':' + c.querySelectorAll('.board-card').length),
            summary: document.getElementById('boardSummary').textContent,
            boards: [...document.querySelectorAll('#boardSelect option')].map(o => o.textContent),
            listHidden: document.getElementById('listView').classList.contains('hidden'),
            chips: [...document.querySelectorAll('.filter-chip')].map(c => c.textContent),
            firstCard: document.querySelector('.board-column:nth-child(2) .board-card') && document.querySelector('.board-column:nth-child(2) .board-card').innerText,
            draggable: document.querySelector('.board-card').draggable,
        })""")
        print(json.dumps(state, ensure_ascii=False, indent=1))
        check(state["wide"], "desktop: app widens for the board")
        check(state["columns"] == ["Por hacer:1", "Haciendo:1", "Hecho:4"], "desktop: 3 columns with 1/1/4 cards")
        check(state["boards"] == ["Mi tablero", "Escuela", "＋ Nuevo tablero…"], "board selector lists both boards, then 'Nuevo tablero'")
        check(state["listHidden"], "list view hidden by default")
        check(state["draggable"], "cards draggable with a mouse")
        check("6h 57m" in state["summary"], "summary shows 6h 57m total")
        await b.shot("desk_board")

        # Tag filter: documentación = Corrección (4h) + kanban (0) -> 2 tasks, 4h 0m (no double count)
        await b.js("[...document.querySelectorAll('.filter-chip')].find(c => c.textContent.includes('documentación')).click()")
        await asyncio.sleep(0.3)
        await b.js("[...document.querySelectorAll('.filter-chip')].find(c => c.textContent.includes('administrativa')).click()")
        await asyncio.sleep(0.3)
        s = await b.js("document.getElementById('boardSummary').textContent")
        check(s.startswith("2 tareas · 4h 0m"), f"doc+adm filter: 2 tasks, 4h once ({s})")
        await b.shot("desk_filtered")
        await b.js("document.querySelector('.filter-clear').click()")
        await asyncio.sleep(0.3)

        # Drag "Idea suelta" (Por hacer) to Haciendo with synthetic drag events
        await b.js("""(() => {
            const card = [...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Idea suelta'));
            const target = document.querySelectorAll('.board-column')[1];
            const dt = new DataTransfer();
            card.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
            target.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
            target.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
            card.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer: dt}));
        })()""")
        await asyncio.sleep(1.5)
        _, tl = call("GET", "/api/tasks", expect=200)
        idea = next(t for t in tl["tasks"] if t["title"] == "Idea suelta sin proyecto")
        check(idea["column_id"] == col["Haciendo"], "drag & drop moved the card to Haciendo (saved)")

        # Add a card in Por hacer
        await b.js("""(() => {
            const form = document.querySelector('.board-column .board-add');
            form.querySelector('input').value = 'Tarjeta desde el tablero';
            form.requestSubmit();
        })()""")
        await asyncio.sleep(1.5)
        names = await b.js("[...document.querySelectorAll('.board-column')[0].querySelectorAll('.board-card-title')].map(e => e.textContent)")
        check("Tarjeta desde el tablero" in names, "add card creates it in its column")

        # "Mover a…" select
        await b.js("""(() => {
            const card = [...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Tarjeta desde el tablero'));
            const sel = card.querySelector('.board-card-move');
            sel.value = [...sel.options].find(o => o.textContent === 'Hecho').value;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
        })()""")
        await asyncio.sleep(1.5)
        _, tl = call("GET", "/api/tasks", expect=200)
        t = next(t for t in tl["tasks"] if t["title"] == "Tarjeta desde el tablero")
        check(t["column_id"] == col["Hecho"] and t["is_done"], "'Mover a…' moves to Hecho and marks it done")

        # Board switch
        await b.js("const s = document.getElementById('boardSelect'); s.value = [...s.options].find(o => o.textContent === 'Escuela').value; s.dispatchEvent(new Event('change'))")
        cards = await b.wait_for("[...document.querySelectorAll('.board-card-title')].map(e => e.textContent)",
                                 lambda v: v == ["Capítulo 3: funciones"])
        check(cards == ["Capítulo 3: funciones"], f"switching to Escuela shows its card ({cards})")

        # List view
        await b.js("document.querySelector('[data-projects-view=\"list\"]').click()")
        await asyncio.sleep(0.5)
        lv = await b.js("({list: !document.getElementById('listView').classList.contains('hidden'), board: document.getElementById('boardView').classList.contains('hidden'), wide: document.body.classList.contains('board-wide'), stored: localStorage.getItem('projects_view'), cards: document.querySelectorAll('.project-card').length})")
        check(lv["list"] and lv["board"] and not lv["wide"] and lv["stored"] == "list" and lv["cards"] >= 2, f"list view: shows projects, narrow, remembered ({lv})")
        await b.shot("desk_list")
        await b.js("document.querySelector('[data-projects-view=\"board\"]').click()")
        await asyncio.sleep(0.3)

        # Back to calendar tab: not wide
        await b.js("document.getElementById('tabCalendar').click()")
        await asyncio.sleep(0.5)
        check(not await b.js("document.body.classList.contains('board-wide')"), "calendar tab: app back to narrow")

        # Mobile
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.0)
        m = await b.js("""({
            wide: document.body.classList.contains('board-wide'),
            tabs: [...document.querySelectorAll('.board-column-tab')].map(t => t.textContent + (t.getAttribute('aria-selected') === 'true' ? '*' : '')),
            visibleColumns: [...document.querySelectorAll('.board-column')].filter(c => getComputedStyle(c).display !== 'none').length,
            docWidth: document.documentElement.scrollWidth,
        })""")
        print(json.dumps(m, ensure_ascii=False))
        check(not m["wide"] and m["visibleColumns"] == 1 and m["docWidth"] <= 390, f"mobile: one column, no horizontal overflow ({m})")
        await b.shot("mobile_board")
        await b.js("[...document.querySelectorAll('.board-column-tab')].find(t => t.textContent.startsWith('Hecho')).click()")
        await asyncio.sleep(0.4)
        await b.shot("mobile_board_hecho")

        # Dark theme, desktop
        await b.viewport(1280, 900)
        await b.js("localStorage.setItem('theme', 'dark')")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.0)
        await b.shot("desk_board_dark")
        await b.js("localStorage.removeItem('theme')")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_board():
    asyncio.run(main())
