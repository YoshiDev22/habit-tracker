"""Tablero (BACKLOG 41): ocultar columnas desde la fila "Columnas" de los filtros, plegar los
filtros, y el tiempo de la tarjeta en corto, en la línea de las etiquetas."""
import asyncio
import json

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def column_chip(name):
    return (f"[...document.querySelectorAll('#boardFilters [data-filter-column]')]"
            f".find(c => c.textContent.startsWith({json.dumps(name + ' · ')}))")


SHOWN = "[...document.querySelectorAll('#boardColumns .board-column')].map(c => c.querySelector('.board-column-name').textContent)"


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    _, bl = call("GET", "/api/boards", expect=200)
    names = [c["name"] for c in bl["boards"][0]["columns"]]
    _, pl = call("GET", "/api/projects", expect=200)
    project = next(p["name"] for p in pl["projects"] if not p["is_system"])
    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/api/health")   # mismo origen, sin arrancar la app
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('board_selected')")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for(f"{SHOWN}.length === {len(names)}")

        # La fila Columnas: un chip por columna, todas encendidas (encendido = se ve)
        st = await b.js("""({row: [...document.querySelectorAll('#boardFilters .filter-row-label')].map(l => l.textContent),
            pressed: [...document.querySelectorAll('#boardFilters [data-filter-column]')].map(c => c.getAttribute('aria-pressed')),
            toggle: document.querySelector('#boardFilters .filters-toggle').textContent})""")
        check("Columnas" in st["row"] and st["pressed"] == ["true"] * len(names) and st["toggle"] == "▾ Filtros",
              f"a Columnas row with every column on ({st})")

        # El tiempo va con las etiquetas: la línea del título solo tiene título y ▶
        st = await b.js("""(() => { const c = document.querySelector('.board-card');
            return {head: !!c.querySelector('.board-card-head .board-card-time'), meta: !!c.querySelector('.board-card-meta .board-card-time')}; })()""")
        check(st == {"head": False, "meta": True}, f"the card time sits with the tags, not by the title ({st})")

        # Apagar la última: se oculta, el resumen dice que hay filtro y aparece "× Mostrar todas"
        last = names[-1]
        await b.js(f"{column_chip(last)}.click()")
        await b.wait_for(f"!{SHOWN}.includes({json.dumps(last)})")
        st = await b.js("""({shown: %s, showAll: !!document.querySelector('.filter-show-columns'),
            summary: document.getElementById('boardSummary').textContent,
            toggle: document.querySelector('#boardFilters .filters-toggle').textContent,
            move: [...document.querySelector('.board-card-move').options].map(o => o.textContent)})""" % SHOWN)
        check(last not in st["shown"] and st["showAll"] and "(con filtro)" in st["summary"]
              and st["toggle"] == "▾ Filtros · 1 activo" and f"{last} (oculta)" in st["move"],
              f"turning a column off hides it, says so, and 'Mover a…' still offers it ({st})")
        await b.shot("board_columns_hidden", full=False)

        # Se recuerda en este dispositivo, por tablero
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for(f"{SHOWN}.length === {len(names) - 1}")
        check(last not in await b.js(SHOWN), "after reloading the column is still hidden")

        # Siempre queda una: con una sola a la vista, su chip no se apaga
        for name in names[1:-1]:
            await b.js(f"{column_chip(name)}.click()")
        await b.wait_for(f"{SHOWN}.length === 1")
        st = await b.js(f"({{disabled: {column_chip(names[0])}.disabled, shown: {SHOWN}}})")
        await b.js(f"{column_chip(names[0])}.click()")
        await asyncio.sleep(0.3)
        check(st["disabled"] and await b.js(SHOWN) == [names[0]], f"the last column on can't be turned off ({st})")

        # "× Mostrar todas" devuelve las columnas y no toca el filtro de proyectos
        await b.js(f"[...document.querySelectorAll('#boardFilters [data-filter-project]')].find(c => c.textContent.includes({json.dumps(project)})).click()")
        await b.wait_for("document.querySelector('#boardFilters [data-filter-project][aria-pressed=true]')")
        await b.js("document.querySelector('.filter-show-columns').click()")
        await b.wait_for(f"{SHOWN}.length === {len(names)}")
        st = await b.js("""({showAll: !!document.querySelector('.filter-show-columns'),
            project: !!document.querySelector('#boardFilters [data-filter-project][aria-pressed=true]')})""")
        check(st == {"showAll": False, "project": True}, f"'× Mostrar todas' only brings the columns back ({st})")

        # Plegar los filtros: solo el botón, con cuántos hay activos; se recuerda
        await b.js("document.querySelector('#boardFilters .filters-toggle').click()")
        await b.wait_for("!document.querySelector('#boardFilters .filter-row')")
        folded = await b.js("document.querySelector('#boardFilters .filters-toggle').textContent")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for("!!document.querySelector('#boardFilters .filters-toggle')")
        still = await b.js("!document.querySelector('#boardFilters .filter-row')")
        check(folded == "▸ Filtros · 1 activo" and still, f"the filters fold to one line that counts them, and stay folded ({folded})")
        await b.shot("board_filters_folded", full=False)
        await b.js("document.querySelector('#boardFilters .filters-toggle').click()")
        await b.wait_for("!!document.querySelector('#boardFilters .filter-row')")

        # En el teléfono: una columna oculta tampoco sale en las pestañas, y nada se sale de lado
        await b.viewport(390, 844, mobile=True)
        await b.js(f"{column_chip(last)}.click()")
        await b.wait_for(f"![...document.querySelectorAll('.board-column-tab')].some(t => t.textContent.startsWith({json.dumps(last + ' ')}))")
        wide = await b.js("document.documentElement.scrollWidth")
        tabs = await b.js("[...document.querySelectorAll('.board-column-tab')].length")
        check(tabs == len(names) - 1 and wide <= 390, f"on a phone the hidden column leaves the tabs too ({tabs} tabs, {wide}px)")
        await b.shot("board_columns_phone", full=True)

        # Son de esta cuenta: cerrar sesión las olvida
        await b.js("handleLogout()")
        await b.wait_for("localStorage.getItem('board_hidden_columns') === null")
        check(await b.js("localStorage.getItem('board_hidden_columns')") is None, "logging out forgets the hidden columns")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_board_columns():
    asyncio.run(main())
