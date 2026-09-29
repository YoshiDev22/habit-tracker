"""Calendario v2, fase 4: leyenda con los lugares de los puntos, días futuros atenuados,
descanso distinto de protegido y la racha de cada hábito en "Este mes"."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
REST_DAY = TODAY - timedelta(days=9)          # sin hábitos y en día de descanso
TOMORROW = TODAY + timedelta(days=1)


async def main():
    login("leyenda@test.com")
    token = api.TOKEN
    for key, label, color in (("gym", "Gimnasio", "#e74c3c"), ("lectura", "Lectura de novelas largas", "#3498db"),
                              ("dieta", "Dieta", "#27ae60")):
        call("POST", "/api/habits/definitions", {"key": key, "label": label, "color": color}, expect=201)
    call("PATCH", "/api/auth/me", {"rest_days": [REST_DAY.weekday()]}, expect=200)
    # 7 días de Gym (hace 2 a 8) ganan un escudo, que cubre ayer
    for i in range(2, 9):
        call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i)}", {"habit_key": "gym", "done": True}, expect=200)
    _, st = call("GET", f"/api/habits/streak?today={TODAY}", expect=200)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    cell_style = """((d) => { const c = document.querySelector(`.day-cell[data-date="${d}"]`);
        if (!c) return null; const s = getComputedStyle(c);
        const dot = c.querySelector('.habit-dot');
        return {bg: s.backgroundColor, shadow: s.boxShadow, opacity: s.opacity, classes: c.className,
                dotOpacity: dot ? getComputedStyle(dot).opacity : null}; })"""

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.wait_for("document.querySelectorAll('#habitLegend .legend-item').length", lambda n: n == 3)

        legend = await b.js("""({
            names: [...document.querySelectorAll('#habitLegend .legend-name')].map(e => e.textContent),
            columns: getComputedStyle(document.getElementById('habitLegend')).gridTemplateColumns.split(' ').length,
            dotCols: document.querySelector('.habit-dots').style.getPropertyValue('--dots-per-row'),
            truncated: (() => { const e = [...document.querySelectorAll('#habitLegend .legend-name')][1];
                                return e.scrollWidth > e.clientWidth; })(),
            bottom: document.getElementById('habitLegend').getBoundingClientRect().bottom,
            pageWidth: document.documentElement.scrollWidth,
        })""")
        check(legend["names"] == ["Gimnasio", "Lectura de novelas largas", "Dieta"],
              f"legend lists the month's habits in dot order ({legend['names']})")
        check(legend["columns"] == 3 and legend["dotCols"] == "3", f"legend uses the dots' columns ({legend['columns']} / {legend['dotCols']})")
        check(legend["truncated"], "a long name is cut with an ellipsis instead of wrapping")
        check(legend["pageWidth"] <= 390 and legend["bottom"] <= 844,
              f"strip, bar, calendar and legend fit at 390 px without scrolling (bottom {legend['bottom']:.0f})")

        if YESTERDAY.month == TODAY.month:
            prot = await b.js(f"{cell_style}('{YESTERDAY}')")
            check("protected" in prot["classes"] and prot["shadow"] != "none", f"the protected day has its own look ({prot})")
        if REST_DAY.month == TODAY.month:
            rest = await b.js(f"{cell_style}('{REST_DAY}')")
            check("rest-day" in rest["classes"] and float(rest["opacity"]) < 1, f"the rest day is dimmed ({rest})")
            if YESTERDAY.month == TODAY.month:
                check(rest["bg"] != prot["bg"] and rest["shadow"] != prot["shadow"],
                      "rest and protected days no longer look the same")
        if TOMORROW.month == TODAY.month:
            fut = await b.js(f"{cell_style}('{TOMORROW}')")
            check("future" in fut["classes"] and abs(float(fut["dotOpacity"]) - 0.16) < 0.01,
                  f"future days show faint dots ({fut['dotOpacity']})")
        now = await b.js(f"{cell_style}('{TODAY}')")
        check(float(now["dotOpacity"]) == 1, "today's dots are not faded")

        cards = await b.js("""[...document.querySelectorAll('#statsGrid .stat-card')].map(c => [
            c.querySelector('.stat-label').textContent, (c.querySelector('.stat-streak') || {}).textContent || ''])""")
        exp_gym = st["habit_streaks"].get("gym", 0)
        check(cards[0] == ["Gimnasio", f"🔥{exp_gym}"] and cards[1][1] == "" and cards[2][1] == "",
              f"'Este mes' shows each habit's own streak when alive ({cards}; API gym {exp_gym})")
        cols = await b.js("getComputedStyle(document.getElementById('statsGrid')).gridTemplateColumns.split(' ').length")
        check(cols == 3, f"'Este mes' uses the same columns as the dots ({cols})")
        # Ayer lo cubrió un escudo, así que la app pregunta: se contesta para ver el calendario
        await b.js("document.getElementById('missedDaySkipBtn').click()")
        await asyncio.sleep(0.3)
        await b.shot("calendar_legend", full=True)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_calendar_legend():
    asyncio.run(main())
