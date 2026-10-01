import asyncio
import json
import sys

from api import call, wait_api
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

KANBAN = "Revisión de idea para cambiar a kanban"


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    def api_task(title):
        _, tl = call("GET", "/api/tasks", expect=200)
        return next(t for t in tl["tasks"] if t["title"] == title)

    async def open_card(title):
        await b.js(f"[...document.querySelectorAll('.board-card')].find(c => c.querySelector('.board-card-title').textContent === {json.dumps(title)}).click()")
        await asyncio.sleep(1.0)

    async def confirm_yes():
        await asyncio.sleep(0.3)
        await b.js("document.getElementById('confirmModalConfirmBtn').click()")
        await asyncio.sleep(1.0)

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view'); localStorage.removeItem('board_selected');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.0)

        await open_card(KANBAN)
        st = await b.js("""({
            open: !document.getElementById('cardModal').classList.contains('hidden'),
            title: document.getElementById('cardTitle').value,
            progress: document.getElementById('cardChecklistProgress').textContent,
            items: document.querySelectorAll('.card-check-row').length,
            comment: document.querySelector('.card-comment') && document.querySelector('.card-comment').innerText,
            columnGroups: [...document.querySelectorAll('#cardColumn optgroup')].map(g => g.label),
            project: document.getElementById('cardProject').selectedOptions[0].textContent,
            tagsOn: [...document.querySelectorAll('#cardTagRow .card-tag-chip')].map(c => c.textContent),
        })""")
        print(json.dumps(st, ensure_ascii=False))
        check(st["open"] and st["title"] == KANBAN, "click opens the card detail")
        check(st["progress"] == "1/3" and st["items"] == 3, "checklist loaded (1/3)")
        check(st["comment"] and "Yoshio" in st["comment"] and "Investigar GTD" in st["comment"], "comment shows author and text")
        check(st["columnGroups"] == ["Mi tablero", "Escuela"], "column select offers every board")
        check(st["project"] == "Habit Tracker" and st["tagsOn"] == ["documentación"], "project and tags preselected")
        await b.shot("card_desktop", full=False)

        # Title + description (blur saves)
        await b.js("""(() => {
            const t = document.getElementById('cardTitle'); t.focus(); t.value = 'Rediseño kanban'; t.blur();
            const n = document.getElementById('cardNotes'); n.focus(); n.value = 'Tablero con columnas por tablero'; n.blur();
        })()""")
        await asyncio.sleep(1.5)
        t = api_task("Rediseño kanban")
        check(t["notes"] == "Tablero con columnas por tablero", "title and description saved on blur")

        # Project -> Sin asignar, tag toggle, new tag
        await b.js("""(() => {
            const s = document.getElementById('cardProject');
            s.value = [...s.options].find(o => o.textContent === 'Sin asignar').value;
            s.dispatchEvent(new Event('change'));
        })()""")
        await asyncio.sleep(1.0)
        await b.js("document.querySelector('#cardTagRow .card-tag-add').click()")
        await asyncio.sleep(0.4)
        await b.js("[...document.querySelectorAll('.tag-picker-row')].find(r => r.textContent.includes('administrativa')).click()")
        await asyncio.sleep(1.0)
        await b.js("""(() => {
            document.getElementById('tagPickerName').value = 'examen'; document.getElementById('tagPickerForm').requestSubmit();
        })()""")
        await asyncio.sleep(1.5)
        t = api_task("Rediseño kanban")
        _, tags = call("GET", "/api/tags", expect=200)
        names = {x["id"]: x["name"] for x in tags["tags"]}
        check(t["project_id"] != col and sorted(names[i] for i in t["tag_ids"]) == ["administrativa", "documentación", "examen"],
              f"project changed, tag toggled, new tag created and attached ({[names[i] for i in t['tag_ids']]})")
        _, pl = call("GET", "/api/projects", expect=200)
        un = next(p for p in pl["projects"] if p["is_system"])
        check(t["project_id"] == un["id"], "project is now Sin asignar")

        # Checklist: add, toggle, delete
        await b.js("""(() => {
            const f = document.getElementById('cardChecklistForm'); f.querySelector('input').value = 'Probar en el teléfono'; f.requestSubmit();
        })()""")
        await asyncio.sleep(1.0)
        await b.js("""(() => {
            const row = [...document.querySelectorAll('.card-check-row')].find(r => r.innerText.includes('Definir columnas'));
            const cb = row.querySelector('input'); cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true}));
        })()""")
        await asyncio.sleep(1.0)
        await b.js("[...document.querySelectorAll('.card-check-row')].find(r => r.innerText.includes('Diseñar tarjetas')).querySelector('.card-check-delete').click()")
        await asyncio.sleep(1.0)
        _, cl = call("GET", f"/api/tasks/{t['id']}/checklist", expect=200)
        got = [(i["text"], i["is_done"]) for i in cl["items"]]
        check(got == [("Leer artículos de Trello", True), ("Definir columnas", True), ("Probar en el teléfono", False)], f"checklist add/toggle/delete ({got})")
        prog = await b.js("document.getElementById('cardChecklistProgress').textContent")
        check(prog == "2/3", f"progress updates live ({prog})")

        # Comments: add (newest first), delete own
        await b.js("""(() => {
            const f = document.getElementById('cardCommentForm'); f.querySelector('textarea').value = 'Listo el backend'; f.requestSubmit();
        })()""")
        await asyncio.sleep(1.0)
        first = await b.js("document.querySelector('.card-comment .card-comment-body').textContent")
        check(first == "Listo el backend", "new comment appears first")
        await b.js("[...document.querySelectorAll('.card-comment')].find(c => c.innerText.includes('Investigar GTD')).querySelector('.card-comment-delete').click()")
        await confirm_yes()
        cm = await wait_api(f"/api/tasks/{t['id']}/comments", lambda body: len(body["comments"]) == 1)
        check([c["body"] for c in cm["comments"]] == ["Listo el backend"], "own comment deleted after confirm")

        # Move to Hecho via column select, close, board reflects it
        await b.js(f"""(() => {{
            const s = document.getElementById('cardColumn'); s.value = '{col["Hecho"]}'; s.dispatchEvent(new Event('change'));
        }})()""")
        await asyncio.sleep(1.0)
        await b.js("document.getElementById('closeCardModalBtn').click()")
        await asyncio.sleep(2.0)
        card = await b.js("""(() => {
            const cols = [...document.querySelectorAll('.board-column')];
            const hecho = cols.find(c => c.querySelector('.board-column-name').textContent === 'Hecho');
            const card = [...hecho.querySelectorAll('.board-card')].find(c => c.innerText.includes('Rediseño kanban'));
            return card ? card.innerText : null;
        })()""")
        check(card is not None and "☑ 2/3" in card and "💬 1" in card and "examen" in card and "Sin asignar" in card,
              f"board shows the edited card in Hecho with its badges ({card!r})")
        check(api_task("Rediseño kanban")["is_done"], "moving to Hecho marked it done")
        await b.shot("board_after_edit", full=False)

        # Timer: manual log preselects the (done) task
        await open_card("Rediseño kanban")
        await b.js("document.querySelector('#cardTimer [data-timer=manual]').click()")
        await asyncio.sleep(1.5)
        lt = await b.js("""({
            card: document.getElementById('cardModal').classList.contains('hidden'),
            log: !document.getElementById('logTimeModal').classList.contains('hidden'),
            task: document.getElementById('logTimeTask').selectedOptions[0].textContent,
        })""")
        check(not lt["card"] and lt["log"] and lt["task"] == "Rediseño kanban", f"manual log opens with the done task selected ({lt})")
        await b.js("document.getElementById('closeLogTimeBtn').click()")
        await asyncio.sleep(0.5)

        # Timer: pomodoro from the card
        await open_card("Rediseño kanban")
        await b.js("document.querySelector('#cardTimer [data-timer=focus]').click()")
        await asyncio.sleep(1.5)
        pm = await b.js("({status: pomoState.status, mode: pomoState.mode, task: pomoState.taskTitle})")
        check(pm == {"status": "running", "mode": "focus", "task": "Rediseño kanban"}, f"pomodoro starts on the card's task ({pm})")
        check(api_task("Rediseño kanban")["column_id"] == col["Hecho"], "starting the timer doesn't move the card")
        await b.js("stopTimer({skipConfirm: true})")
        await b.js("document.getElementById('closeCardModalBtn').click()")
        await asyncio.sleep(1.0)

        # Keyboard: Enter on a focused card opens it; Escape closes
        await b.js("document.querySelector('.board-card').focus()")
        await b.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13)
        await asyncio.sleep(1.0)
        opened = await b.js("!document.getElementById('cardModal').classList.contains('hidden')")
        await b.send("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        await asyncio.sleep(1.0)
        closed = await b.js("document.getElementById('cardModal').classList.contains('hidden')")
        check(opened and closed, "Enter opens a focused card, Escape closes it")

        # Delete a card
        await open_card("Idea suelta sin proyecto")
        await b.js("document.getElementById('cardDeleteBtn').click()")
        await confirm_yes()
        _, tl = call("GET", "/api/tasks", expect=200)
        check(all(x["title"] != "Idea suelta sin proyecto" for x in tl["tasks"]), "delete card after confirm")

        # Mobile + dark
        await b.viewport(390, 844, mobile=True)
        await b.js("localStorage.setItem('theme', 'dark')")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.0)
        await b.js("[...document.querySelectorAll('.board-column-tab')].find(t => t.textContent.startsWith('Hecho')).click()")
        await asyncio.sleep(0.3)
        await open_card("Rediseño kanban")
        fits = await b.js("(() => { const r = document.querySelector('.card-modal').getBoundingClientRect(); return r.left >= 0 && r.right <= 390; })()")
        check(fits, "card detail fits a 390px phone")
        await b.shot("card_mobile_dark", full=False)
        await b.js("localStorage.removeItem('theme')")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_card():
    asyncio.run(main())
