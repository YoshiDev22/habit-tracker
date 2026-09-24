import asyncio
import json
import sys

import api
from api import call, login
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE


def column_titles(col_id):
    _, tl = call("GET", "/api/tasks", expect=200)
    return [t["title"] for t in tl["tasks"] if t["column_id"] == col_id]


# Drag `title` and drop it in column `col_index`, before the card `before`
# (None = at the end), with the pointer where a real mouse would be.
def drag_js(title, col_index, before):
    before_js = "null" if before is None else json.dumps(before)
    return f"""(() => {{
        const card = [...document.querySelectorAll('.board-card')].find(c => c.querySelector('.board-card-title').textContent === {json.dumps(title)});
        const column = document.querySelectorAll('.board-column')[{col_index}];
        const beforeTitle = {before_js};
        let y;
        if (beforeTitle) {{
            const b = [...column.querySelectorAll('.board-card')].find(c => c.querySelector('.board-card-title').textContent === beforeTitle);
            y = b.getBoundingClientRect().top + 2;
        }} else {{
            const cards = column.querySelectorAll('.board-card');
            const last = cards[cards.length - 1];
            y = last ? last.getBoundingClientRect().bottom + 2 : column.getBoundingClientRect().top + 60;
        }}
        const dt = new DataTransfer();
        card.dispatchEvent(new DragEvent('dragstart', {{bubbles: true, dataTransfer: dt}}));
        column.dispatchEvent(new DragEvent('dragover', {{bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}}));
        const shown = !!column.querySelector('.drop-indicator');
        column.dispatchEvent(new DragEvent('drop', {{bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}}));
        card.dispatchEvent(new DragEvent('dragend', {{bubbles: true, dataTransfer: dt}}));
        return shown;
    }})()"""


async def main():
    token, col = seed()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    hecho = ["Corrección de Pomodoros", "Confirmación de cambios datos y cancelación pomodoro",
             "Confirmación de guardado de datos en hábitos", "modificación de tiempo de pomodoros"]
    check(column_titles(col["Hecho"]) == hecho, "starting order of Hecho")

    # --- API
    _, t = call("POST", "/api/tasks", {"title": "Nueva al final", "column_id": col["Hecho"]}, expect=201)
    check(column_titles(col["Hecho"])[-1] == "Nueva al final", "a new card lands at the end of its column")
    _, tl = call("GET", "/api/tasks", expect=200)
    ids = {x["title"]: x["id"] for x in tl["tasks"]}
    order = [ids[n] for n in ["Nueva al final"] + hecho]
    call("POST", "/api/tasks/reorder", {"column_id": col["Hecho"], "task_ids": order}, expect=204)
    check(column_titles(col["Hecho"])[0] == "Nueva al final", "reorder endpoint saves the column order")
    check(call("POST", "/api/tasks/reorder", {"column_id": col["Hecho"], "task_ids": order + [order[0]]})[0] == 422, "duplicates -> 422")
    check(call("POST", "/api/tasks/reorder", {"column_id": col["Por hacer"], "task_ids": order})[0] == 422, "tasks from another column -> 422")
    call("PATCH", f"/api/tasks/{ids['Nueva al final']}", {"column_id": col["Por hacer"]}, expect=200)
    check(column_titles(col["Por hacer"])[-1] == "Nueva al final", "moving to another column puts it at the end")
    call("PATCH", f"/api/tasks/{ids['Nueva al final']}", {"is_done": True}, expect=200)
    check(column_titles(col["Hecho"])[-1] == "Nueva al final", "ticking it sends it to the end of Hecho")
    mine = api.TOKEN
    login("otro@test.com")
    check(call("POST", "/api/tasks/reorder", {"column_id": col["Hecho"], "task_ids": order})[0] == 404, "another user can't reorder my column")
    api.TOKEN = mine
    call("DELETE", f"/api/tasks/{ids['Nueva al final']}", expect=204)

    # --- Board: drag within and across columns
    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await asyncio.sleep(1.2)

        shown = await b.js(drag_js("modificación de tiempo de pomodoros", 2, "Corrección de Pomodoros"))
        await asyncio.sleep(1.8)
        got = column_titles(col["Hecho"])
        check(shown and got[0] == "modificación de tiempo de pomodoros" and len(got) == 4,
              f"drag the last card to the top of its column (indicator shown: {shown})")
        dom = await b.js("[...document.querySelectorAll('.board-column')[2].querySelectorAll('.board-card-title')].map(e => e.textContent)")
        check(dom == got, "the board shows the saved order after refreshing")

        await b.js(drag_js("Corrección de Pomodoros", 2, "Confirmación de guardado de datos en hábitos"))
        await asyncio.sleep(1.8)
        got = column_titles(col["Hecho"])
        check(got == ["modificación de tiempo de pomodoros", "Confirmación de cambios datos y cancelación pomodoro",
                      "Corrección de Pomodoros", "Confirmación de guardado de datos en hábitos"],
              f"drop between two cards ({got})")

        await b.js(drag_js("Confirmación de cambios datos y cancelación pomodoro", 0, "Idea suelta sin proyecto"))
        await asyncio.sleep(1.8)
        got = column_titles(col["Por hacer"])
        _, tl = call("GET", "/api/tasks", expect=200)
        moved = next(t for t in tl["tasks"] if t["title"] == "Confirmación de cambios datos y cancelación pomodoro")
        check(got == ["Confirmación de cambios datos y cancelación pomodoro", "Idea suelta sin proyecto"] and not moved["is_done"],
              f"drag into another column at a position; it stops being done ({got})")

        await b.js(drag_js("Idea suelta sin proyecto", 0, None))
        await asyncio.sleep(1.2)
        check(column_titles(col["Por hacer"])[-1] == "Idea suelta sin proyecto", "drop at the end of the column")

        # Organizar: drag a column by its handle
        await b.js("document.getElementById('boardConfigBtn').click()")
        await asyncio.sleep(1.5)
        handles = await b.js("document.querySelectorAll('#configColumns .config-drag').length")
        await b.js("""(() => {
            const rows = [...document.querySelectorAll('#configColumns .config-row')];
            const row = rows.find(r => r.querySelector('.config-name').value === 'Hecho');
            const target = rows.find(r => r.querySelector('.config-name').value === 'Por hacer');
            row.querySelector('.config-drag').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
            const dt = new DataTransfer();
            row.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
            const y = target.getBoundingClientRect().top + 2;
            const list = document.getElementById('configColumns');
            list.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}));
            list.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt, clientY: y}));
            row.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer: dt}));
        })()""")
        await asyncio.sleep(1.8)
        _, bl = call("GET", "/api/boards", expect=200)
        names = [c["name"] for c in bl["boards"][0]["columns"]]
        rows = await b.js("[...document.querySelectorAll('#configColumns .config-name')].map(i => i.value)")
        check(handles == 3 and names == ["Hecho", "Por hacer", "Haciendo"] and rows == names,
              f"drag a column by its handle to the first place ({names})")
        left = await b.js("document.querySelectorAll('#configColumns .config-row[draggable=\"true\"]').length")
        check(left == 0, "rows stop being draggable after the drop")
        await b.shot("config_drag", full=False)
        await b.js("document.getElementById('closeBoardConfigBtn').click()")
        await asyncio.sleep(1.5)
        board_cols = await b.js("[...document.querySelectorAll('.board-column-name')].map(e => e.textContent)")
        check(board_cols == ["Hecho", "Por hacer", "Haciendo"], f"the board follows the new column order ({board_cols})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_reorder():
    asyncio.run(main())
