import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Idea suelta'))"
ROWS = "[...document.querySelectorAll('.tag-picker-row')].map(r => r.querySelector('.tag-picker-name').textContent + (r.classList.contains('on') ? '✓' : ''))"
CHIPS = "[...document.querySelectorAll('#cardTagRow .card-tag-chip')].map(c => c.textContent)"
PICKER_OPEN = "!document.getElementById('tagPicker').classList.contains('hidden')"


async def main():
    token, col = seed()
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def js(expr, wait=0.6):
        r = await b.js(expr)
        await asyncio.sleep(wait)
        return r

    def task_tags():
        _, tl = call("GET", "/api/tasks", expect=200)
        _, tg = call("GET", "/api/tags", expect=200)
        names = {x["id"]: (x["name"], x["color"]) for x in tg["tags"]}
        t = next(t for t in tl["tasks"] if t["title"] == "Idea suelta sin proyecto")
        return sorted(names[i] for i in t["tag_ids"])

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        await js(f"{CARD}.click()", wait=1.0)

        st = await b.js(f"({{chips: {CHIPS}, add: document.querySelector('#cardTagRow .card-tag-add').textContent, open: {PICKER_OPEN}, section: !!document.getElementById('cardTags')}})")
        check(st == {"chips": [], "add": "+ Etiqueta", "open": False, "section": False},
              f"no tags: just a discreet '+ Etiqueta' under the title, no big section ({st})")

        await js("document.querySelector('#cardTagRow .card-tag-add').click()", wait=0.4)
        st = await b.js(f"({{open: {PICKER_OPEN}, rows: {ROWS}, focus: document.activeElement.id}})")
        check(st == {"open": True, "rows": ["administrativa", "documentación"], "focus": "tagPickerName"},
              f"+ opens the list with the existing tags, focus on the new-tag box ({st})")
        await b.shot("tagpicker_open", full=False)

        # Click on the row (not a checkbox) toggles on, and again off
        await js("[...document.querySelectorAll('.tag-picker-row')].find(r => r.textContent.includes('documentación')).querySelector('.tag-picker-name').click()", wait=1.0)
        st = await b.js(f"({{rows: {ROWS}, chips: {CHIPS}, open: {PICKER_OPEN}}})")
        check(st == {"rows": ["administrativa", "documentación✓"], "chips": ["documentación"], "open": True}
              and task_tags() == [("documentación", "#8e44ad")],
              f"clicking a tag's name toggles it on; chip appears, list stays open ({st})")
        await js("[...document.querySelectorAll('.tag-picker-row')].find(r => r.textContent.includes('documentación')).click()", wait=1.0)
        check(task_tags() == [] and await b.js(CHIPS) == [], "clicking the row again toggles it off")

        # Typing filters; Enter creates with the chosen colour
        await js("(() => { const n = document.getElementById('tagPickerName'); n.value = 'adm'; n.dispatchEvent(new Event('input')); })()", wait=0.3)
        check(await b.js(ROWS) == ["administrativa"], "typing filters the list")
        await js("(() => { const n = document.getElementById('tagPickerName'); n.value = 'urgente'; n.dispatchEvent(new Event('input')); })()", wait=0.3)
        hint = await b.js("document.querySelector('.tag-picker-empty').textContent")
        check(hint == 'Enter para crear "urgente"', f"no match suggests creating it ({hint})")
        await js("document.getElementById('tagPickerColor').value = '#e74c3c'; document.getElementById('tagPickerForm').requestSubmit()", wait=1.2)
        st = await b.js(f"({{rows: {ROWS}, chips: {CHIPS}, box: document.getElementById('tagPickerName').value, focus: document.activeElement.id}})")
        check(("urgente", "#e74c3c") in task_tags() and "urgente" in st["chips"] and st["box"] == "" and st["focus"] == "tagPickerName"
              and "urgente✓" in st["rows"], f"Enter creates the tag with its colour and applies it ({st})")

        # An existing name (other case) is reused, not duplicated
        await js("document.getElementById('tagPickerName').value = 'ADMINISTRATIVA'; document.getElementById('tagPickerForm').requestSubmit()", wait=1.2)
        _, tg = call("GET", "/api/tags", expect=200)
        check([t["name"] for t in tg["tags"]].count("administrativa") == 1 and any(n == "administrativa" for n, _ in task_tags()),
              "typing an existing name reuses that tag")
        await b.shot("tagpicker_used", full=False)

        # Escape closes only the picker; clicking outside closes it too
        await b.send("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        await asyncio.sleep(0.4)
        st = await b.js(f"({{picker: {PICKER_OPEN}, modal: !document.getElementById('cardModal').classList.contains('hidden')}})")
        check(st == {"picker": False, "modal": True}, f"Escape closes the picker, not the card ({st})")
        await js("document.querySelector('#cardTagRow .card-tag-chip').click()", wait=0.3)
        check(await b.js(PICKER_OPEN), "clicking a chip opens the picker too")
        await js("document.getElementById('cardNotes').click()", wait=0.3)
        check(not await b.js(PICKER_OPEN), "clicking elsewhere in the card closes the picker")

        # The board card shows the new tags after closing
        await js("document.getElementById('closeCardModalBtn').click()", wait=1.5)
        text = await b.js(f"{CARD}.innerText")
        check("urgente" in text and "administrativa" in text, f"board card shows the tags ({text!r})")

        # Phone
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        await js("[...document.querySelectorAll('.board-column-tab')].find(t => t.textContent.startsWith('Por hacer')).click()", wait=0.3)
        await js(f"{CARD}.click()", wait=1.0)
        await js("document.querySelector('#cardTagRow .card-tag-add').click()", wait=0.4)
        fits = await b.js("(() => { const r = document.getElementById('tagPicker').getBoundingClientRect(); return r.left >= 0 && r.right <= 390; })()")
        check(fits, "picker fits a phone")
        await b.shot("tagpicker_mobile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_tagpicker():
    asyncio.run(main())
