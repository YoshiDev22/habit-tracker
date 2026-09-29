"""Calendario v2, fase 5: el popover del día. Cada hábito en su color (aro sin marcar,
relleno con halo marcado), el mismo orden que los puntos, y un pie con "N de M hoy" y
el estado del día (descanso o escudo)."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
REST_DAY = TODAY - timedelta(days=9)
COLORS = {"gym": "rgb(231, 76, 60)", "lectura": "rgb(52, 152, 219)", "dieta": "rgb(39, 174, 96)"}


async def main():
    login("popover@test.com")
    token = api.TOKEN
    for key, color in (("gym", "#e74c3c"), ("lectura", "#3498db"), ("dieta", "#27ae60")):
        call("POST", "/api/habits/definitions", {"key": key, "label": key.title(), "color": color}, expect=201)
    call("PATCH", "/api/auth/me", {"rest_days": [REST_DAY.weekday()]}, expect=200)
    for i in range(2, 9):          # 7 días de Gym: un escudo, que cubre ayer
        call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i)}", {"habit_key": "gym", "done": True}, expect=200)
    call("PATCH", f"/api/habits/day/{TODAY}", {"habit_key": "lectura", "done": True}, expect=200)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def open_day(d):
        await b.js("hideHabitPopover()")
        await b.js(f"document.querySelector('.day-cell[data-date=\"{d}\"]').click()")
        await asyncio.sleep(0.3)
        return await b.js("""({
            order: [...document.querySelectorAll('#habitsList .habit-btn')].map(x => x.dataset.habit),
            rows: [...document.querySelectorAll('#habitsList .habit-btn')].map(x => {
                const s = getComputedStyle(x.querySelector('.habit-dot'));
                return {habit: x.dataset.habit, done: x.classList.contains('completed'),
                        fill: s.backgroundColor, ring: s.borderTopColor, opacity: s.opacity, halo: s.boxShadow};
            }),
            count: document.getElementById('popoverCount').textContent,
            state: document.getElementById('popoverState').textContent,
        })""")

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('missedDaySkipBtn').click()")   # ayer lo cubrió un escudo
        await asyncio.sleep(0.3)

        dots = await b.js(f"[...document.querySelectorAll('.day-cell[data-date=\"{TODAY}\"] .habit-dot')].map(d => [...d.classList].find(c => c !== 'habit-dot' && c !== 'active'))")
        p = await open_day(TODAY)
        check(p["order"] == dots == ["gym", "lectura", "dieta"], f"popover order equals the dots' ({p['order']} / {dots})")
        rows = {r["habit"]: r for r in p["rows"]}
        lec, gym = rows["lectura"], rows["gym"]
        check(lec["done"] and lec["fill"] == COLORS["lectura"] and lec["opacity"] == "1" and lec["halo"] != "none",
              f"a marked habit: filled in its color with a halo ({lec})")
        check(not gym["done"] and gym["fill"] == "rgba(0, 0, 0, 0)" and gym["ring"] == COLORS["gym"]
              and abs(float(gym["opacity"]) - 0.55) < 0.01, f"an unmarked habit: only its ring, faint ({gym})")
        check(p["count"] == "1 de 3 hoy" and p["state"] == "", f"footer for today ({p['count']!r}, {p['state']!r})")
        await b.shot("day_popover_today", full=False)

        if YESTERDAY.month == TODAY.month:
            p = await open_day(YESTERDAY)
            check(p["count"] == "0 de 3" and "escudo" in p["state"], f"a protected day says so ({p['count']!r}, {p['state']!r})")
        if REST_DAY.month == TODAY.month:
            p = await open_day(REST_DAY)
            check(p["state"] == "Día de descanso", f"a rest day says so ({p['state']!r})")

        # Marcar desde el popover sigue funcionando y guarda solo ese par
        await open_day(TODAY)
        await b.js("document.querySelector('#habitsList .habit-btn[data-habit=\"gym\"]').click()")
        await asyncio.sleep(1.2)
        p = await open_day(TODAY)
        check(p["count"] == "2 de 3 hoy", f"marking updates the count ({p['count']!r})")
        _, h = call("GET", f"/api/habits?today={TODAY}", expect=200)
        day = next(e["habits_data"] for e in h["entries"] if e["date"] == TODAY.isoformat())
        check(day == {"lectura": True, "gym": True}, f"only that pair was saved ({day})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_day_popover():
    asyncio.run(main())
