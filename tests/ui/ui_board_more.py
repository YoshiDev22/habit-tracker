"""Tablero (1.24): una columna con muchas tarjetas muestra de 10 en 10, con su
propio scroll, y la página no crece sin fin."""
import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    _, boards = api.call("GET", "/api/boards", expect=200)
    board = boards["boards"][0]
    column = board["columns"][0]
    _, existing = api.call("GET", f"/api/tasks?board_id={board['id']}", expect=200)
    already = sum(1 for t in existing["tasks"] if t["column_id"] == column["id"])
    for i in range(25):
        api.call("POST", "/api/tasks", {"title": f"Tarea {i + 1:02d}", "column_id": column["id"]}, expect=201)
    total = already + 25
    sel = f".board-column[data-column-id='{column['id']}']"
    cards = f"document.querySelectorAll(\"{sel} .board-card\").length"
    more = f"(document.querySelector(\"{sel} [data-more=more]\") || {{}}).textContent"

    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});"
                   f" localStorage.setItem('board_selected', '{board['id']}')")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await b.js("document.getElementById('tabProjects').click()")
        await b.wait_for(f"{cards} > 0")
        check(await b.js(cards) == 10, f"a column shows 10 cards ({await b.js(cards)})")
        text = await b.js(more)
        check(text == f"Mostrar 10 más (quedan {total - 10})", f"and offers 10 more ({text})")

        await b.js(f"document.querySelector(\"{sel} [data-more=more]\").click()")
        check(await b.wait_for(f"{cards} === 20"), "Mostrar 10 más adds ten")
        await b.js(f"document.querySelector(\"{sel} [data-more=more]\").click()")
        await b.wait_for(f"{cards} === {min(30, total)}")
        st = await b.js(f"""(() => {{ const list = document.querySelector("{sel} .board-cards");
            return {{scrolls: list.scrollHeight > list.clientHeight + 5, height: list.clientHeight, max: window.innerHeight * 0.7,
                     less: Boolean(document.querySelector("{sel} [data-more=less]"))}}; }})()""")
        check(st["scrolls"] and st["height"] <= st["max"] + 1 and st["less"],
              f"expanded, the column scrolls inside instead of growing the page ({st})")
        await b.shot("board_more_expanded", full=False)

        # Soltar debajo de la última que se ve: queda delante de la primera oculta
        await b.js(f"document.querySelector(\"{sel} [data-more=less]\").click()")
        await b.wait_for(f"{cards} === 10")
        st = await b.js(f"""(() => {{ const col = document.querySelector("{sel}");
            return {{before: dropBeforeId(col, null), firstHidden: Number(col.dataset.firstHidden)}}; }})()""")
        check(st["before"] == st["firstHidden"] and st["before"], f"dropping below the last shown card keeps it there ({st})")

        # Una tarjeta nueva va al final: la columna se expande hasta ella
        await b.js(f"""(() => {{ const input = document.querySelector("{sel} .board-add input");
            input.value = 'Tarjeta nueva'; input.form.requestSubmit(); }})()""")
        await b.wait_for(f"[...document.querySelectorAll(\"{sel} .board-card\")].some(c => c.textContent.includes('Tarjeta nueva'))",
                         timeout=10)
        seen = await b.js(f"""(() => {{ const list = document.querySelector("{sel} .board-cards");
            const card = [...list.querySelectorAll('.board-card')].find(c => c.textContent.includes('Tarjeta nueva'));
            const a = list.getBoundingClientRect(), r = card.getBoundingClientRect();
            return r.top >= a.top - 1 && r.bottom <= a.bottom + 1; }})()""")
        check(seen, "a new card is shown at the end, scrolled into its column")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_board_more():
    asyncio.run(main())
