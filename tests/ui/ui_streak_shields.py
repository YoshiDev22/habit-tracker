import asyncio
import json
from datetime import date, timedelta

import api
from api import call, login
from cdp import Browser

BASE = api.BASE
TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def seed(email, offsets):
    """Una cuenta con un hábito hecho los días `offsets` (hace N días)."""
    login(email)
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "icon": "🏋️"}, expect=201)
    for i in offsets:
        call("POST", "/api/habits", {"date": (TODAY - timedelta(days=i)).isoformat(), "habits": {"gym": True}}, expect=200)
    return api.TOKEN


STATE = f"""(() => {{
    const modal = document.getElementById('missedDayModal');
    const cell = document.querySelector('.day-cell[data-date="{YESTERDAY}"]');
    return {{
        asking: !modal.classList.contains('hidden'),
        text: document.getElementById('missedDayText').textContent,
        habits: [...document.querySelectorAll('#missedDayHabits .habit-option')].map(r => r.textContent),
        streak: document.getElementById('streakCount').textContent,
        shields: document.getElementById('streakShields').textContent,
        cellShown: !!cell,
        protectedCell: !!cell && cell.classList.contains('protected') && !!cell.querySelector('.day-shield'),
    }};
}})()"""


async def open_app(b, token):
    await b.goto(BASE + "/")
    await b.js(f"localStorage.clear(); localStorage.setItem('access_token', {json.dumps(token)});")
    await b.goto(BASE + "/", wait=2.5)


async def main():
    shielded = seed("shield@test.com", range(2, 9))    # 7 días y ayer vacío: un protector lo cubre
    broken = seed("broken@test.com", (2, 3))            # 2 días y ayer vacío: se corta
    b = Browser()
    await b.start()
    results = []

    def check(cond, label):
        results.append(("OK  " if cond else "FAIL") + " " + label)

    try:
        await b.viewport(390, 844, mobile=True)

        # --- Un protector cubrió ayer ---
        await open_app(b, shielded)
        s = await b.js(STATE)
        check(s["asking"], "asks about yesterday on opening the app")
        check("protector" in s["text"] and "7 días" in s["text"], f"says a shield kept the 7-day streak ({s['text']})")
        check(s["habits"] == ["🏋️ Gym"], f"offers the habits to mark ({s['habits']})")
        check(s["streak"] == "7", f"streak stays at 7 ({s['streak']})")
        check(s["shields"] == "🛡️ Protector en 7 días de racha", f"no shield left, next in 7 ({s['shields']})")
        if s["cellShown"]:
            check(s["protectedCell"], "yesterday's cell shows the shield")
        await b.shot("shields_asking", full=False)

        await b.js("document.getElementById('missedDaySaveBtn').click()")
        await asyncio.sleep(0.4)
        err = await b.js("document.getElementById('missedDayError').textContent")
        check("Marca" in err, f"nothing checked: asks to mark something ({err})")

        await b.js("document.querySelector('#missedDayHabits input').click()")
        await b.js("document.getElementById('missedDaySaveBtn').click()")
        await asyncio.sleep(1.2)
        s = await b.js(STATE)
        check(not s["asking"], "saving closes the question")
        check(s["streak"] == "8", f"streak goes on to 8 ({s['streak']})")
        check(s["shields"] == "🛡️ 1 protector · otro en 6 días", f"the shield comes back ({s['shields']})")
        if s["cellShown"]:
            check(not s["protectedCell"], "yesterday's cell no longer shows the shield")
        await b.shot("shields_saved", full=False)

        await b.goto(BASE + "/", wait=2.5)
        s = await b.js(STATE)
        check(not s["asking"], "after answering, a reload does not ask again")

        # --- La racha se cortó ayer; "No, no lo hice" ---
        await open_app(b, broken)
        s = await b.js(STATE)
        check(s["asking"] and "se cortó" in s["text"] and "2 días" in s["text"], f"says the 2-day streak broke ({s['text']})")
        check(s["streak"] == "0", f"streak is 0 ({s['streak']})")
        await b.js("document.getElementById('missedDaySkipBtn').click()")
        await asyncio.sleep(0.3)
        s = await b.js(STATE)
        check(not s["asking"], "'No, no lo hice' closes it")
        await b.goto(BASE + "/", wait=2.5)
        s = await b.js(STATE)
        check(not s["asking"], "and it is not asked again for that day")
        check(s["streak"] == "0", "nothing was marked")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_streak_shields():
    asyncio.run(main())
