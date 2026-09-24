import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    def boards():
        _, bl = call("GET", "/api/boards?include_inactive=true", expect=200)
        return {x["name"]: x for x in bl["boards"]}

    async def js(expr, wait=1.0):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    async def set_row_input(container, match, cls, value):
        await js(f"""(() => {{
            const row = [...document.querySelectorAll('#{container} .config-row')].find(r => {{
                const n = r.querySelector('.config-name'); return (n.value || n.textContent) === {json.dumps(match)};
            }});
            const input = row.querySelector('.{cls}');
            input.value = {json.dumps(value)};
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
        }})()""")

    async def row_click(container, match, cls, confirm=False):
        await js(f"""(() => {{
            const row = [...document.querySelectorAll('#{container} .config-row')].find(r => {{
                const n = r.querySelector('.config-name'); return (n.value || n.textContent) === {json.dumps(match)};
            }});
            row.querySelector('.{cls}').click();
        }})()""", wait=0.5)
        if confirm:
            await js("document.getElementById('confirmModalConfirmBtn').click()", wait=1.2)

    async def error_text():
        return await b.js("(() => { const e = document.getElementById('boardConfigError'); return e.classList.contains('hidden') ? '' : e.textContent; })()")

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view'); localStorage.removeItem('board_selected');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()")

        # "+ Nuevo tablero…" opens Organizar focused on the new-board field
        await js("""(() => { const s = document.getElementById('boardSelect'); s.value = 'new'; s.dispatchEvent(new Event('change')); })()""", wait=1.5)
        st = await b.js("({open: !document.getElementById('boardConfigModal').classList.contains('hidden'), focus: document.activeElement.id, select: document.getElementById('boardSelect').selectedOptions[0].textContent, boards: [...document.querySelectorAll('#configBoards .config-name')].map(i => i.value)})")
        check(st["open"] and st["focus"] == "configNewBoard" and st["select"] == "Mi tablero", f"'Nuevo tablero…' opens Organizar with focus, select unchanged ({st})")
        check(st["boards"] == ["Mi tablero", "Escuela"], "lists active boards")

        # Create "Ventas"
        await js("""(() => { const f = document.getElementById('configBoardForm'); document.getElementById('configNewBoard').value = 'Ventas'; f.requestSubmit(); })()""", wait=1.5)
        cols = await b.js("({board: document.getElementById('configColumnsBoard').selectedOptions[0].textContent, cols: [...document.querySelectorAll('#configColumns .config-name')].map(i => i.value)})")
        check("Ventas" in boards() and cols == {"board": "Ventas", "cols": ["Por hacer", "Haciendo", "Hecho"]}, f"new board created with default columns and selected for editing ({cols})")

        # Columns of Ventas: add Bloqueado (doing), rename, recolor, reorder, delete
        await js("""(() => { const f = document.getElementById('configColumnForm'); f.querySelector('input[type=text]').value = 'Bloqueado'; f.requestSubmit(); })()""", wait=1.5)
        await set_row_input("configColumns", "Por hacer", "config-name", "Backlog")
        await set_row_input("configColumns", "Backlog", "config-color", "#123456")
        await row_click("configColumns", "Bloqueado", 'config-move[data-delta=\\"-1\\"]')
        await asyncio.sleep(1.0)
        v = boards()["Ventas"]
        got = [(c["name"], c["category"], c["color"]) for c in v["columns"]]
        check(got == [("Backlog", "todo", "#123456"), ("Haciendo", "doing", "#3498db"), ("Bloqueado", "doing", None), ("Hecho", "done", "#2ecc71")],
              f"add / rename / recolor / move up columns ({got})")
        await b.shot("config_desktop", full=False)

        await row_click("configColumns", "Bloqueado", "config-delete-column")
        await asyncio.sleep(1.0)
        check([c["name"] for c in boards()["Ventas"]["columns"]] == ["Backlog", "Haciendo", "Hecho"], "delete an empty column")
        await row_click("configColumns", "Hecho", "config-delete-column")
        await asyncio.sleep(1.0)
        err = await error_text()
        check("única" in err and "Hecho" in [c["name"] for c in boards()["Ventas"]["columns"]], f"last 'Terminado' column is protected, error shown ({err})")

        # Rename Escuela, archive + restore Ventas, delete Mi tablero (has tasks) -> error
        await set_row_input("configBoards", "Escuela", "config-name", "Escuela 2026")
        check("Escuela 2026" in boards(), "rename board")
        await row_click("configBoards", "Ventas", "config-archive-board")
        await asyncio.sleep(1.0)
        archived = await b.js("[...document.querySelectorAll('#configArchivedBoards .config-name')].map(e => e.textContent)")
        check(archived == ["Ventas"] and not boards()["Ventas"]["is_active"], "archive board -> listed as archived")
        await row_click("configArchivedBoards", "Ventas", "config-restore-board")
        await asyncio.sleep(1.0)
        check(boards()["Ventas"]["is_active"], "restore archived board")
        await row_click("configBoards", "Mi tablero", "config-delete-board", confirm=True)
        err = await error_text()
        check("tareas" in err and "Mi tablero" in boards(), f"board with tasks can't be deleted, error shown ({err})")

        # Close -> board select shows Ventas selected, board reloaded
        await js("document.getElementById('closeBoardConfigBtn').click()", wait=2.0)
        after = await b.js("({select: [...document.querySelectorAll('#boardSelect option')].map(o => o.textContent), current: document.getElementById('boardSelect').selectedOptions[0].textContent, columns: [...document.querySelectorAll('.board-column-name')].map(e => e.textContent)})")
        check(after["current"] == "Ventas" and after["columns"] == ["Backlog", "Haciendo", "Hecho"] and "Escuela 2026" in after["select"],
              f"after closing, board shows Ventas with its columns ({after})")

        # Delete the (empty) Ventas board from Organizar; the board falls back
        await js("document.getElementById('boardConfigBtn').click()", wait=1.5)
        await row_click("configBoards", "Ventas", "config-delete-board", confirm=True)
        check("Ventas" not in boards(), "delete empty board after confirm")
        await b.send("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        await asyncio.sleep(2.0)
        fb = await b.js("({closed: document.getElementById('boardConfigModal').classList.contains('hidden'), current: document.getElementById('boardSelect').selectedOptions[0].textContent})")
        check(fb["closed"] and fb["current"] == "Mi tablero", f"Escape closes; deleted current board falls back to the first ({fb})")

        # Mobile look
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()")
        await js("document.getElementById('boardConfigBtn').click()", wait=1.5)
        fits = await b.js("(() => { const r = document.querySelector('.config-modal').getBoundingClientRect(); return r.left >= 0 && r.right <= 390 && document.querySelector('.config-modal').scrollWidth <= document.querySelector('.config-modal').clientWidth; })()")
        check(fits, "Organizar fits a phone without sideways scroll")
        await b.shot("config_mobile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_config():
    asyncio.run(main())
