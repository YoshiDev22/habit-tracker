import asyncio
import json
import sys

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

BAR = ("({hidden: pomodoroBar.classList.contains('hidden'), message: pomodoroBar.classList.contains('message'), "
       "label: pomodoroBarLabel.textContent, time: pomodoroBarTime.classList.contains('hidden') ? null : pomodoroBarTime.textContent, "
       "actions: [...pomodoroBarActions.querySelectorAll('button')].map(b => b.textContent)})")
KANBAN_CARD = "[...document.querySelectorAll('.board-card')].find(c => c.innerText.includes('Revisión de idea'))"


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

    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('projects_view'); localStorage.removeItem('board_selected'); localStorage.removeItem('pomodoro_sound');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)

        st = await b.js("({tab: document.getElementById('tabProjects').textContent, card: !!document.querySelector('.pomodoro-card'), today: document.getElementById('pomoToday').textContent, inToolbar: !!document.querySelector('.board-toolbar #pomoSoundBtn')})")
        check(st == {"tab": "Tableros", "card": False, "today": st["today"] if st["today"].startswith("Hoy: ") else None, "inToolbar": True},
              f"tab renamed, no timer card, 'Hoy' and sound in the toolbar ({st})")
        await b.shot("timer_toolbar", full=False)

        await js("document.getElementById('pomoSoundBtn').click()", wait=0.2)
        snd = await b.js("({icon: document.getElementById('pomoSoundBtn').textContent, stored: localStorage.getItem('pomodoro_sound')})")
        await js("document.getElementById('pomoSoundBtn').click()", wait=0.2)
        check(snd == {"icon": "🔇", "stored": "0"}, f"sound toggle still works ({snd})")

        # ▶ on a card: bar shows the task, card marked
        await js(f"{KANBAN_CARD}.querySelector('.board-card-play').click()", wait=1.2)
        r = await b.js(BAR)
        marked = await b.js("[...document.querySelectorAll('.board-card.timing')].map(c => c.querySelector('.board-card-title').textContent)")
        check(not r["hidden"] and not r["message"] and r["label"] == "Cronómetro · Revisión de idea para cambiar a kanban" and r["time"] is not None,
              f"▶ starts the stopwatch, bar names the task ({r})")
        check(marked == ["Revisión de idea para cambiar a kanban"], f"the timed card is highlighted ({marked})")
        await b.shot("timer_running", full=False)

        # Stop under a minute -> message, then it goes away. Pin the start 10 s
        # ago so a slow run can't cross the 1 minute threshold.
        await js("pomoState.startedEpochMs = Date.now() - 10000; savePomoState(); pomodoroBarStopBtn.click()", wait=0.8)
        r = await b.js(BAR)
        check(r["message"] and r["label"] == "Tiempo descartado (menos de 1 minuto)." and r["time"] is None,
              f"stopping shows a message in the bar ({r})")
        await asyncio.sleep(5.5)
        check(await b.js("pomodoroBar.classList.contains('hidden')"), "the message hides by itself")

        # Focus pomodoro from the card detail, forced to end now
        today_before = await b.js("document.getElementById('pomoToday').textContent")
        await js(f"{KANBAN_CARD}.click()", wait=1.0)
        await js("document.querySelector('#cardTimer [data-timer=focus]').click()", wait=1.0)
        await js("pomoState.targetEpochMs = Date.now() + 300; savePomoState();", wait=2.5)
        r = await b.js(BAR)
        check(r["message"] and r["label"] == "¡Pomodoro completado!" and r["actions"] == ["Descanso 5 min", "15 min", "Ahora no"],
              f"finishing a pomodoro offers a break ({r})")
        today = await b.js("document.getElementById('pomoToday').textContent")
        def minutes(text):
            t = text.replace("Hoy: ", "").strip()
            h = int(t.split("h")[0]) if "h" in t else 0
            m = int(t.split("h")[-1].replace("m", "").strip() or 0)
            return h * 60 + m
        check(minutes(today) - minutes(today_before) == 25, f"the 25 min were saved and 'Hoy' updated ({today_before} -> {today})")
        await b.shot("timer_break_offer", full=False)

        await js("[...pomodoroBarActions.querySelectorAll('button')].find(b => b.textContent === 'Descanso 5 min').click()", wait=1.0)
        r = await b.js(BAR)
        check(not r["message"] and r["label"] == "Descanso" and r["time"] in ("05:00", "04:59"),
              f"'Descanso 5 min' starts a 5 minute break ({r})")
        await js("pomodoroBarStopBtn.click()", wait=1.0)
        check(await b.js("pomoState.status") == "idle", "a break stops without asking")

        # 'Ahora no' dismisses the offer
        await js(f"{KANBAN_CARD}.click()", wait=1.0)
        await js("document.querySelector('#cardTimer [data-timer=focus]').click()", wait=1.0)
        await js("pomoState.targetEpochMs = Date.now() + 300; savePomoState();", wait=2.5)
        await js("[...pomodoroBarActions.querySelectorAll('button')].find(b => b.textContent === 'Ahora no').click()", wait=0.5)
        check(await b.js("pomodoroBar.classList.contains('hidden') && pomoState.status === 'idle'"), "'Ahora no' closes the offer")

        # List view ▶ names the task too
        await js("document.querySelector('[data-projects-view=\"list\"]').click()", wait=0.6)
        await js("[...document.querySelectorAll('.project-card')].find(c => c.querySelector('.project-name').textContent === 'Habit Tracker').querySelector('.project-toggle').click()", wait=1.5)
        await js("document.querySelector('.task-row:not(.done) .task-play').click()", wait=1.0)
        label = await b.js("pomodoroBarLabel.textContent")
        check(label.startswith("Cronómetro · "), f"list ▶ also names the task ({label})")
        await js("pomodoroBarStopBtn.click()", wait=0.5)
        await js("document.querySelector('[data-projects-view=\"board\"]').click()", wait=0.3)

        # Mobile toolbar
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        await js("document.getElementById('tabProjects').click()", wait=1.0)
        w = await b.js("document.documentElement.scrollWidth")
        check(w <= 390, f"mobile toolbar fits ({w}px)")
        await b.shot("timer_mobile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_timer():
    asyncio.run(main())
