"""Edit checklist items and comments in place from the card detail."""
import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

KANBAN_CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Revisión de idea'))"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def key(target, k, ctrl=False):
    return (f"{target}.dispatchEvent(new KeyboardEvent('keydown', {{key: '{k}', ctrlKey: {str(ctrl).lower()}, "
            "bubbles: true, cancelable: true}))")


ROWS = "[...document.querySelectorAll('#cardChecklist .card-check-row')]"
INPUT = "document.querySelector('#cardChecklist .card-inline-edit')"


async def main():
    token, _ = seed()
    _, tl = call("GET", "/api/tasks", expect=200)
    kanban = next(t for t in tl["tasks"] if t["title"].startswith("Revisión de idea"))

    def items():
        _, d = call("GET", f"/api/tasks/{kanban['id']}/checklist", expect=200)
        return {i["id"]: (i["text"], i["is_done"]) for i in d["items"]}

    b = Browser()
    await b.start()

    async def js(expr, wait=0.0):
        r = await b.js(expr)
        if wait:
            await asyncio.sleep(wait)
        return r

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.2)
        await js(f"{KANBAN_CARD}.click()", wait=1.5)

        before = items()
        done_id = next(i for i, (t, d) in before.items() if d)
        ids = [int(x) for x in await js(f"{ROWS}.map(r => r.dataset.itemId)")]

        # Enter saves, keeps it checked
        await js(f"{ROWS}[0].querySelector('.card-check-edit').click()", wait=0.3)
        focused = await js(f"document.activeElement === {INPUT}")
        await js(f"{INPUT}.value = 'Leer artículos de Trello y Jira'; " + key(INPUT, "Enter"), wait=1.2)
        after = items()
        row0 = await js(f"({{text: {ROWS}[0].querySelector('span').textContent, checked: {ROWS}[0].querySelector('input[type=checkbox]').checked}})")
        check(focused and after[ids[0]] == ("Leer artículos de Trello y Jira", before[ids[0]][1]) and row0["text"] == "Leer artículos de Trello y Jira",
              f"✎ + Enter saves the text and keeps it checked ({after[ids[0]]}, {row0})")

        # Escape cancels and does not close the card
        await js(f"{ROWS}[1].querySelector('.card-check-edit').click()", wait=0.3)
        await js(f"{INPUT}.value = 'no debería guardarse'; " + key(INPUT, "Escape"), wait=0.8)
        st = await js("({open: !document.getElementById('cardModal').classList.contains('hidden'), editing: !!" + INPUT + "})")
        check(items()[ids[1]] == before[ids[1]] and st == {"open": True, "editing": False},
              f"Escape cancels, the card stays open ({items()[ids[1]]}, {st})")

        # Leaving the field saves
        await js(f"{ROWS}[2].querySelector('.card-check-edit').click()", wait=0.3)
        await js(f"{INPUT}.value = 'Diseñar tarjetas v2'; document.getElementById('cardNotes').focus();", wait=1.2)
        check(items()[ids[2]][0] == "Diseñar tarjetas v2", f"leaving the field saves ({items()[ids[2]]})")

        # Empty text is ignored
        await js(f"{ROWS}[2].querySelector('.card-check-edit').click()", wait=0.3)
        await js(f"{INPUT}.value = '   '; " + key(INPUT, "Enter"), wait=0.8)
        check(items()[ids[2]][0] == "Diseñar tarjetas v2", "an empty text leaves it as it was")

        # Comment: Editar -> Guardar
        await js("document.querySelector('#cardComments .card-comment-edit').click()", wait=0.3)
        ta = "document.querySelector('#cardComments .card-comment-edit-form textarea')"
        await js(f"{ta}.value = 'Investigar GTD, Personal Kanban y Scrumban';", wait=0.1)
        await js("document.querySelector('#cardComments .card-comment-save').click()", wait=1.2)
        _, cs = call("GET", f"/api/tasks/{kanban['id']}/comments", expect=200)
        c = cs["comments"][0]
        shown = await js("document.querySelector('#cardComments .card-comment').textContent")
        check(c["body"] == "Investigar GTD, Personal Kanban y Scrumban" and c["edited_at"] and "· editado" in shown
              and "Scrumban" in shown, f"editing a comment saves it and marks it edited ({c['body']}, {shown[:80]})")

        # Ctrl+Enter saves, Escape cancels without closing the card
        await js("document.querySelector('#cardComments .card-comment-edit').click()", wait=0.3)
        await js(f"{ta}.value = 'cancelado'; " + key(ta, "Escape"), wait=0.6)
        st = await js("({open: !document.getElementById('cardModal').classList.contains('hidden'), body: document.querySelector('#cardComments .card-comment-body').textContent})")
        check(st == {"open": True, "body": "Investigar GTD, Personal Kanban y Scrumban"}, f"Escape cancels the comment edit ({st})")
        await js("document.querySelector('#cardComments .card-comment-edit').click()", wait=0.3)
        await js(f"{ta}.value = 'Investigar GTD'; " + key(ta, "Enter", ctrl=True), wait=1.2)
        _, cs = call("GET", f"/api/tasks/{kanban['id']}/comments", expect=200)
        check(cs["comments"][0]["body"] == "Investigar GTD", f"Ctrl+Enter saves ({cs['comments'][0]['body']})")

        # Reopen the card: the edits are there
        await js("document.getElementById('closeCardModalBtn').click()", wait=1.2)
        await js(f"{KANBAN_CARD}.click()", wait=1.5)
        r = await js("({first: " + ROWS + "[0].querySelector('span').textContent, meta: document.querySelector('#cardComments .card-comment-meta').textContent})")
        check(r["first"] == "Leer artículos de Trello y Jira" and "editado" in r["meta"], f"after reopening the card ({r})")
        icons = await js("[...document.querySelectorAll('#cardComments .card-comment-meta button')].map(b => [b.textContent, b.getAttribute('aria-label')])")
        check(icons == [["✎", "Editar comentario"], ["×", "Eliminar comentario"]], f"comment actions are icons ({icons})")
        count = await js("document.getElementById('cardCommentsCount').textContent")
        check(count == "· 1", f"the section shows how many ({count})")
        # Hide the comments; it is remembered when the card is reopened
        await js("document.getElementById('cardCommentsToggle').click()", wait=0.3)
        hid = await js("[document.getElementById('cardCommentsBody').classList.contains('hidden'), document.getElementById('cardCommentsToggle').getAttribute('aria-expanded')]")
        await js("document.getElementById('closeCardModalBtn').click()", wait=1.0)
        await js(f"{KANBAN_CARD}.click()", wait=1.5)
        still = await js("document.getElementById('cardCommentsBody').classList.contains('hidden')")
        check(hid == [True, "false"] and still, f"comments can be hidden and stay hidden ({hid}, reopened hidden={still})")
        await b.shot("comments_hidden", full=False)
        await js("document.getElementById('cardCommentsToggle').click()", wait=0.3)
        check(not await js("document.getElementById('cardCommentsBody').classList.contains('hidden')"), "and shown again")
        await b.shot("inline_edit", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_inline_edit():
    asyncio.run(main())
