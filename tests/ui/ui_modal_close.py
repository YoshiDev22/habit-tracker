"""Every modal's × is clickable at its center: nothing painted after it covers it.

The headers with a ‹ (Configuración, Mi perfil, Reportes guardados) are
position: relative and come after the × in the HTML, so without a z-index on
the × they were painted over it and only its right edge took the click.
"""
import asyncio
import json

import api
from api import login
from cdp import Browser

BASE = api.BASE

# For each visible .modal-close: is the element at its center the button itself?
COVERED = """(() => {
    const bad = [];
    const modals = [...document.querySelectorAll('.modal')];
    modals.forEach(m => m.classList.add('hidden'));
    // One at a time, so one modal never covers another's ×
    modals.forEach(modal => {
        modal.classList.remove('hidden');
        modal.querySelectorAll('.modal-close').forEach(btn => {
            const r = btn.getBoundingClientRect();
            if (!r.width) return;
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            if (!btn.contains(hit)) {
                bad.push(`${modal.id}: ${hit ? (hit.id || hit.className || hit.tagName) : 'nothing'}`);
            }
        });
        modal.classList.add('hidden');
    });
    return bad;
})()"""


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        for width, height, mobile in ((1280, 800, False), (390, 844, True)):
            await b.viewport(width, height, mobile=mobile)
            await b.goto(BASE + "/")
            await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)})")
            await b.goto(BASE + "/", wait=2.5)
            await b.js("document.getElementById('habitsSetupModal').classList.add('hidden')")
            bad = await b.js(COVERED)
            check(not bad, f"{width} px: every × takes the click at its center ({bad or 'all'})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_modal_close():
    asyncio.run(main())
