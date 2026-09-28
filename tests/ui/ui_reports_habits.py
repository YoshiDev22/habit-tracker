"""Reportes: la tarjeta de hábitos cuenta solo los días del rango elegido
(Semana, Mes, el mes anterior y Personalizado)."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()
# Hoy también: así la semana tiene algo que contar aunque sea lunes
GYM = {TODAY - timedelta(days=i) for i in (0, 1, 2, 3, 10, 40, 45)}
LECTURA = {TODAY - timedelta(days=40)}

CARD = """(() => {
    const card = [...document.querySelectorAll('.report-card')].find(c => c.querySelector('.report-streak'));
    if (!card) return null;
    return {
        from: document.getElementById('reportsFrom').value,
        to: document.getElementById('reportsTo').value,
        rows: [...card.querySelectorAll('.report-bar-row')].map(r => [
            r.querySelector('.report-bar-name').textContent, r.querySelector('.report-bar-value').textContent]),
        facts: card.querySelector('.report-streak-facts').textContent,
    };
})()"""


def dd(n):
    return f"{n} {'día' if n == 1 else 'días'}"


def expected(frm, to):
    """Lo que la tarjeta debe decir para ese rango, contado aquí a mano."""
    last = min(to, TODAY)
    elapsed = (last - frm).days + 1 if last >= frm else 0
    inside = lambda days: sum(1 for d in days if frm <= d <= to)

    def value(done):
        return f"{done} de {dd(elapsed)}" if elapsed > 0 and done <= elapsed else dd(done)

    return {
        "rows": [["🏋️ Gym", value(inside(GYM))], ["📚 Lectura", value(inside(LECTURA))]],
        "active": inside(GYM | LECTURA),
        "elapsed": elapsed,
    }


def matches(card, frm, to):
    exp = expected(frm, to)
    facts_ok = (f"Con algún hábito: {exp['active']} de {dd(exp['elapsed'])}" in card["facts"]
                if exp["elapsed"] > 0 else "Con algún hábito" not in card["facts"])
    return card["rows"] == exp["rows"] and facts_ok


async def main():
    login("rangos@test.com")
    token = api.TOKEN
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "icon": "🏋️"}, expect=201)
    call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura", "icon": "📚", "order": 1}, expect=201)
    for day in sorted(GYM | LECTURA):
        call("POST", "/api/habits", {"date": day.isoformat(),
                                     "habits": {"gym": day in GYM, "lectura": day in LECTURA}}, expect=200)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    async def check_range(name, frm, to, inputs=True):
        # En Semana las casillas de fecha no se llenan: ahí solo cuentan los números
        same = lambda c: not inputs or (c["from"] == frm.isoformat() and c["to"] == to.isoformat())
        card = await b.wait_for(CARD, lambda c: c is not None and same(c) and matches(c, frm, to))
        exp = expected(frm, to)
        if inputs:
            check(card is not None and same(card), f"{name}: range {frm} → {to} ({card and (card['from'], card['to'])})")
        check(card is not None and matches(card, frm, to),
              f"{name}: card counts only the range ({card and card['rows']} / {exp['rows']}; {card and card['facts']})")
        # La misma cuenta que la API para ese rango
        _, hr = call("GET", f"/api/habits/report?date_from={frm}&date_to={to}&today={TODAY}", expect=200)
        done = {h["key"]: h["days_done"] for h in hr["habits"]}
        check(done == {"gym": sum(1 for d in GYM if frm <= d <= to), "lectura": sum(1 for d in LECTURA if frm <= d <= to)}
              and hr["active_days"] == exp["active"], f"{name}: API agrees ({done}, active {hr['active_days']})")

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js("document.getElementById('tabReports').click()")

        monday = TODAY - timedelta(days=TODAY.weekday())
        await check_range("week", monday, monday + timedelta(days=6), inputs=False)

        await b.js("document.querySelector('[data-range=month]').click()")
        first = TODAY.replace(day=1)
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        await check_range("month", first, last)

        await b.js("document.getElementById('reportsPrev').click()")
        prev_last = first - timedelta(days=1)
        await check_range("previous month", prev_last.replace(day=1), prev_last)

        await b.js("document.querySelector('[data-range=custom]').click()")
        frm, to = TODAY - timedelta(days=45), TODAY - timedelta(days=38)
        await b.js(f"""(() => {{ const f = document.getElementById('reportsFrom'), t = document.getElementById('reportsTo');
            f.value = '{frm}'; t.value = '{to}'; t.dispatchEvent(new Event('change')); }})()""")
        await check_range("custom", frm, to)
        await b.shot("reports_habits_custom", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_reports_habits():
    asyncio.run(main())
