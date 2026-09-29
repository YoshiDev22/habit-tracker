"""Franja de racha (Calendario v2, fase 3): racha · escudos · récord entre el mes y la
barra, cada número con su etiqueta; la barra del mes dice "Mes"."""
import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()


async def main():
    login("franja@test.com")
    token = api.TOKEN
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    # 9 días seguidos hace tiempo (récord 9, un escudo ganado), luego un corte y 3 días
    for i in list(range(20, 29)) + [1, 2, 3]:
        call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i)}", {"habit_key": "gym", "done": True}, expect=200)
    _, st = call("GET", f"/api/habits/streak?today={TODAY}", expect=200)

    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        s = await b.wait_for("""(() => {
            const strip = document.getElementById('streakStrip');
            const top = el => el.getBoundingClientRect().top;
            return {
                text: strip.innerText.replace(/\\s+/g, ' ').trim(),
                streak: document.getElementById('streakCount').textContent,
                best: document.getElementById('bestStreak').textContent,
                filled: document.querySelectorAll('#streakShields .shield-slot:not(.spent)').length,
                recharge: document.getElementById('shieldRecharge').textContent,
                order: top(document.getElementById('monthTitle')) < top(strip)
                       && top(strip) < top(document.querySelector('.progress-container')),
                barLabel: document.querySelector('.progress-container .progress-label').textContent,
                oldCard: !!document.querySelector('.metrics-section .streak-container'),
                pageWidth: document.documentElement.scrollWidth,
                calendarBottom: document.querySelector('.calendar').getBoundingClientRect().bottom,
            };
        })()""", lambda v: v["streak"] != "0")
        check(s["streak"] == str(st["streak"]) == "3", f"streak from the API ({s['streak']} / {st['streak']})")
        check(s["best"] == str(st["best_streak"]) == "9", f"best streak from the API ({s['best']} / {st['best_streak']})")
        check("racha" in s["text"] and "escudos" in s["text"] and "récord" in s["text"],
              f"every number carries its label ({s['text']})")
        exp_filled = st["streak_shields"]
        check(s["filled"] == exp_filled, f"shields shown as the API says ({s['filled']} / {exp_filled})")
        exp_recharge = f"Recarga en {st['shield_next_in']} días" if st["shield_next_in"] and exp_filled < 2 else ""
        check(s["recharge"] == exp_recharge.replace("en 1 días", "en 1 día"), f"recharge stays visible ({s['recharge']})")
        check(s["order"], "the strip sits between the month and its bar")
        check(s["barLabel"].strip().lower() == "mes", f"the month bar is labelled ({s['barLabel']})")
        check(not s["oldCard"], "the big streak card is gone from Métricas")
        check(s["pageWidth"] <= 390, f"nothing overflows at 390 px ({s['pageWidth']})")
        check(s["calendarBottom"] <= 844, f"strip, bar and calendar fit without scrolling ({s['calendarBottom']:.0f} px)")
        await b.shot("streak_strip", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_streak_strip():
    asyncio.run(main())
