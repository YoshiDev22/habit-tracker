"""Reportes tab. STAGE limits the checks to the first stages while debugging."""
import asyncio
import json
import sys
import datetime as dt

from api import call
from cdp import Browser
from ui_board import seed, CLOSE_WELCOME, BASE

STAGE = 99   # every stage; lower it to run only the first ones while debugging
results = []
# The browser runs in this machine's timezone; sessions are stored in UTC.
LOCAL_OFFSET_H = round(dt.datetime.now().astimezone().utcoffset().total_seconds() / 3600)

STATS_JS = """({
    stats: [...document.querySelectorAll('.report-stat')].map(s => [s.querySelector('.report-stat-value').textContent, s.querySelector('.report-stat-label').textContent]),
    compare: (document.querySelector('.report-compare') || {}).textContent || null,
    bars: document.querySelectorAll('.report-chart .chart-bar').length,
    rest: document.querySelectorAll('.report-chart .chart-rest').length,
    labels: [...document.querySelectorAll('.report-chart .chart-axis:not(.small)')].map(t => t.textContent).filter(t => !t.endsWith('h')),
})"""


CARD = "[...document.querySelectorAll('.report-card')].find(c => c.querySelector('.report-card-title').textContent === 'IDX')"
BARS_JS = """[...(""" + CARD + """).querySelectorAll('.report-bar-row')].map(r =>
    [r.querySelector('.report-bar-name').firstChild.nextSibling.textContent, r.querySelector('.report-bar-value').firstChild.textContent])"""


def parse_dur(text):
    t = text.strip()
    h = int(t.split("h")[0]) if "h" in t else 0
    m = int(t.split("h")[-1].replace("m", "").strip() or 0)
    return h * 60 + m


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


async def swipe(b, x0, x1, y=400):
    await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x0, "y": y}])
    steps = 8
    for i in range(1, steps + 1):
        await b.send("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": x0 + (x1 - x0) * i / steps, "y": y}])
        await asyncio.sleep(0.02)
    await b.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
    await asyncio.sleep(0.6)


async def main():
    token, col = seed()
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())

    # Two weeks back: 2h on its Tuesday and 30m on its Thursday, plus a break that must not count.
    # Not last week: the fixture's data is dated yesterday, which on a Monday is last week.
    _, tl = call("GET", "/api/tasks", expect=200)
    first = tl["tasks"][0]

    def log(day, hour, minutes, mode="focus", source="manual", task=first, minute=0):
        start = dt.datetime.combine(day, dt.time(hour, minute)) - dt.timedelta(hours=LOCAL_OFFSET_H)
        call("POST", "/api/pomodoro", {
            "project_id": task["project_id"], "task_id": task["id"], "session_date": day.isoformat(),
            "started_at": start.isoformat(), "ended_at": (start + dt.timedelta(minutes=minutes)).isoformat(),
            "duration_seconds": minutes * 60, "planned_seconds": minutes * 60, "mode": mode,
            "was_completed": True, "source": source}, expect=201)

    prev_mon = monday - dt.timedelta(days=7)
    old_mon = monday - dt.timedelta(days=14)
    log(old_mon + dt.timedelta(days=1), 10, 120)
    log(old_mon + dt.timedelta(days=3), 16, 30)
    log(old_mon + dt.timedelta(days=3), 17, 15, mode="short_break", source="timer")
    log(old_mon + dt.timedelta(days=2), 13, 60, source="stopwatch", minute=30)   # crosses 14:00
    idea = next(t for t in tl["tasks"] if t["title"] == "Idea suelta sin proyecto")
    log(monday, 9, 45, source="stopwatch", task=idea)   # this week, unassigned project
    call("PATCH", "/api/auth/me", {"rest_days": [5, 6]}, expect=200)
    # Finish the idea today; then check the completed filter at the API level
    call("PATCH", f"/api/tasks/{idea['id']}?today={today}", {"is_done": True}, expect=200)
    _, done_week = call("GET", f"/api/tasks?completed_from={monday}&completed_to={monday + dt.timedelta(days=6)}", expect=200)
    _, done_prev = call("GET", f"/api/tasks?completed_from={monday - dt.timedelta(days=7)}&completed_to={monday - dt.timedelta(days=1)}", expect=200)
    _, done_today = call("GET", f"/api/tasks?completed_from={today}&completed_to={today}", expect=200)
    # The fixture's 4 finished tasks were finished yesterday: this week, or last week on a Monday
    check(len(done_week["tasks"]) + len(done_prev["tasks"]) == 5 and idea["title"] in [t["title"] for t in done_week["tasks"]]
          and [t["title"] for t in done_today["tasks"]] == [idea["title"]],
          f"API: completed_from/to filters by completion date ({len(done_week['tasks'])}, {len(done_prev['tasks'])}, {[t['title'] for t in done_today['tasks']]})")
    # Habits: gym every weekday from last Monday to today (weekend = rest), lectura only this Monday
    call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "icon": "💪", "color": "#e74c3c"}, expect=201)
    call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura", "icon": "📚", "color": "#3498db", "order": 1}, expect=201)
    d = prev_mon
    while d <= today:
        if d.weekday() < 5:
            call("POST", "/api/habits", {"date": d.isoformat(), "habits": {"gym": True, "lectura": d == monday}})
        d += dt.timedelta(days=1)
    elapsed = today.weekday() + 1
    target = sum(1 for i in range(elapsed) if (monday + dt.timedelta(days=i)).weekday() < 5)
    q = f"date_from={monday}&date_to={monday + dt.timedelta(days=6)}&today={today}"
    _, hr = call("GET", f"/api/habits/report?{q}", expect=200)
    _, st_api = call("GET", f"/api/habits/streak?today={today}", expect=200)
    gym = next(h for h in hr["habits"] if h["key"] == "gym")
    lec = next(h for h in hr["habits"] if h["key"] == "lectura")
    check(hr["days_elapsed"] == elapsed and hr["days_elapsed"] - hr["rest_days_elapsed"] == target and hr["active_days"] == target,
          f"API report: {elapsed} days elapsed, {target} to do, active {hr['active_days']}")
    check(gym["days_done"] == target and gym["current_streak"] == 5 + target and gym["best_streak"] == 5 + target,
          f"API: gym streak runs over the weekend rest ({gym})")
    check(lec["days_done"] == 1 and lec["best_streak"] == 1 and lec["current_streak"] == (1 if today.weekday() <= 1 else 0),
          f"API: lectura ({lec})")
    check(hr["streak"] == st_api["streak"], f"API: report streak equals /streak ({hr['streak']} / {st_api['streak']})")
    check(call("GET", f"/api/habits/report?date_from={today}&date_to={monday - dt.timedelta(days=1)}")[0] == 422, "API: reversed range -> 422")
    _, all_tasks = call("GET", "/api/tasks", expect=200)
    check(len(all_tasks["tasks"]) == len(tl["tasks"]), "API: without the filters every task is still listed")
    _, week_sessions = call("GET", f"/api/pomodoro?date_from={monday}&date_to={monday + dt.timedelta(days=6)}", expect=200)
    week_total = sum(s["duration_seconds"] for s in week_sessions["sessions"] if s["mode"] == "focus")
    _, prev_sessions = call("GET", f"/api/pomodoro?date_from={prev_mon}&date_to={prev_mon + dt.timedelta(days=6)}", expect=200)
    prev_total = sum(s["duration_seconds"] for s in prev_sessions["sessions"] if s["mode"] == "focus")

    b = Browser()
    await b.start()
    try:
        await b.viewport(1280, 900)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)});")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # --- Stage 1: tab, navigation, range
        # Costos existe en el HTML pero oculta: solo aparece con el plan Maker
        tabs = await b.js("[...document.querySelectorAll('.tab-btn')].filter(t => !t.hidden).map(t => t.textContent)")
        check(tabs == ["Calendario", "Tableros", "Reportes"], f"three tabs without the Maker plan ({tabs})")
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(1.2)
        st = await b.js("""({view: currentViewIndex, sel: document.getElementById('tabReports').getAttribute('aria-selected'),
            ind: getComputedStyle(document.querySelector('.tab-indicator')).transform,
            indW: document.querySelector('.tab-indicator').getBoundingClientRect().width,
            tabW: document.getElementById('tabReports').getBoundingClientRect().width,
            indX: document.querySelector('.tab-indicator').getBoundingClientRect().left,
            tabX: document.getElementById('tabReports').getBoundingClientRect().left,
            wide: document.body.classList.contains('board-wide'),
            label: document.getElementById('reportsRangeLabel').textContent,
            next: document.getElementById('reportsNext').disabled})""")
        check(st["view"] == 2 and st["sel"] == "true", "clicking Reportes opens the third view")
        check(abs(st["indW"] - st["tabW"]) < 2 and abs(st["indX"] - st["tabX"]) < 2, f"indicator under the Reportes tab ({st['indX']:.0f}/{st['tabX']:.0f})")
        check(not st["wide"], "reports keep the normal width")
        sunday = monday + dt.timedelta(days=6)
        months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
        exp = f"{monday.day} {months[monday.month-1]} – {sunday.day} {months[sunday.month-1]} {sunday.year}"
        check(st["label"] == exp and st["next"], f"this week, Monday first, next disabled ({st['label']} / {exp})")

        if STAGE >= 2:
            s2 = await b.js(STATS_JS)
            h, m = divmod(week_total // 60, 60)
            exp_total = f"{h}h {m}m" if h else f"{m}m"
            check(s2["stats"][0] == [exp_total, "tiempo total"], f"summary total matches the sessions ({s2['stats'][0]} / {exp_total})")
            if prev_total == 0:
                exp_compare = "Sin tiempo registrado en la semana anterior"
            elif abs(week_total - prev_total) < 60:
                exp_compare = "Igual que la semana anterior"
            else:
                exp_compare = ("+" if week_total > prev_total else "−") + "{} vs. la semana anterior"
                h, m = divmod(abs(week_total - prev_total) // 60, 60)
                exp_compare = exp_compare.format(f"{h}h {m}m" if h else f"{m}m")
            check(s2["compare"] == exp_compare, f"comparison with last week ({s2['compare']} / {exp_compare})")
            check(s2["bars"] == len({s['session_date'] for s in week_sessions['sessions'] if s['mode'] == 'focus'}) and s2["rest"] == 2,
                  f"one bar per day with time, Sat+Sun marked as rest ({s2['bars']} bars, {s2['rest']} rest)")
            check(s2["labels"][:7] == ["L", "M", "X", "J", "V", "S", "D"], f"week axis starts on Monday ({s2['labels'][:7]})")
            await b.shot("reports_week", full=True)
        if STAGE >= 6:
            s6 = await b.js("""(() => {
                const card = [...document.querySelectorAll('.report-card')].find(c => c.querySelector('.report-streak'));
                return {pos: [...document.querySelectorAll('.report-card')].indexOf(card),
                        streak: card.querySelector('.streak-count').textContent,
                        facts: card.querySelector('.report-streak-facts').textContent,
                        rows: [...card.querySelectorAll('.report-bar-row')].map(r => [r.querySelector('.report-bar-name').textContent,
                               r.querySelector('.report-bar-value').textContent, r.querySelector('.report-habit-meta').textContent,
                               r.querySelector('.report-bar-fill').style.width])};
            })()""")
            dd = lambda n: f"{n} {'día' if n == 1 else 'días'}"
            check(s6["pos"] == 1 and s6["streak"] == str(5 + target), f"habits card second, streak {s6['streak']}")
            check(s6["rows"][0] == ["💪 Gym", f"{target} de {dd(target)}", f"🔥 {dd(5 + target)} seguidos · récord {dd(5 + target)}", "100%"],
                  f"gym row ({s6['rows'][0]})")
            check(s6["rows"][1][:2] == ["📚 Lectura", f"1 de {dd(target)}"], f"lectura row ({s6['rows'][1]})")
            check(f"Con algún hábito: {target} de {dd(elapsed)}" in s6["facts"], f"days with a habit ({s6['facts']})")
        if STAGE >= 5:
            s5 = await b.js("""(() => {
                const card = [...document.querySelectorAll('.report-card')].find(c => c.querySelector('.report-tasks'));
                return {stat: document.querySelectorAll('.report-stat')[3].textContent,
                        small: (document.querySelector('.report-compare-small') || {}).textContent || null,
                        rows: [...card.querySelectorAll('.report-task')].map(r => [r.querySelector('.report-task-title').textContent,
                               r.querySelector('.report-task-meta').textContent, r.querySelector('.report-task-date').textContent])};
            })()""")
            n, n_prev = len(done_week["tasks"]), len(done_prev["tasks"])
            exp_stat = f"{n}{'tarea terminada' if n == 1 else 'tareas terminadas'}"
            diff = n - n_prev
            exp_small = (f"{'+' if diff > 0 else '−'}{abs(diff)} {'tarea' if abs(diff) == 1 else 'tareas'} vs. la semana anterior"
                         if diff else None)
            check(s5["stat"] == exp_stat, f"summary counts the finished tasks ({s5['stat']} / {exp_stat})")
            check(s5["small"] == exp_small, f"task comparison ({s5['small']} / {exp_small})")
            check(len(s5["rows"]) == n and s5["rows"][0][0] == idea["title"] and s5["rows"][0][1] == "Sin asignar",
                  f"list: newest first, unassigned labelled ({s5['rows'][:2]})")

        if STAGE >= 3:
            # Per project: must add up to the total; compare with the API summary per project
            _, summ = call("GET", "/api/projects/summary", expect=200)
            bars = await b.js(BARS_JS.replace("IDX", "Por proyecto"))
            proj_sum = sum(parse_dur(r[1]) for r in bars)
            check(proj_sum == week_total // 60, f"project bars add up to the total ({proj_sum} min vs {week_total // 60})")
            check(bars and bars[-1][0] == "Sin asignar" and parse_dur(bars[-1][1]) == 45,
                  f"'Sin asignar' goes last with its 45m ({bars})")
            tag_rows = await b.js(BARS_JS.replace("IDX", "Por etiqueta"))
            _, ts = call("GET", f"/api/tags/summary?date_from={monday}&date_to={monday + dt.timedelta(days=6)}", expect=200)
            exp_tags = sorted([(t["name"], t["total_seconds"] // 60) for t in ts["summaries"] if t["total_seconds"] > 0], key=lambda x: -x[1])
            got_tags = [(r[0], parse_dur(r[1])) for r in tag_rows if not r[0].startswith("Sin etiqueta")]
            check(got_tags == exp_tags, f"tag rows match the API ({got_tags} / {exp_tags})")
            # choose two tags -> combined total without double counting
            await b.js("[..." + CARD.replace("IDX", "Por etiqueta") + ".querySelectorAll('.report-bar-row.selectable')].slice(0, 2).forEach(r => r.click())")
            await asyncio.sleep(1.5)
            note = await b.js("(" + CARD.replace("IDX", "Por etiqueta") + ".querySelector('.report-note.strong') || {}).textContent || null")
            ids = [t["tag_id"] for t in ts["summaries"] if t["total_seconds"] > 0][:2]
            if len(ids) >= 2:
                q = "&".join(f"tag_ids={i}" for i in ids)
                _, both = call("GET", f"/api/tags/summary?date_from={monday}&date_to={monday + dt.timedelta(days=6)}&{q}", expect=200)
                h, m = divmod(both["combined_seconds"] // 60, 60)
                exp = f"{h}h {m}m" if h else f"{m}m"
                check(note is not None and exp in note, f"two tags: combined once ({note} / {exp})")
            pressed = await b.js("" + CARD.replace("IDX", "Por etiqueta") + ".querySelectorAll('[aria-pressed=true]').length")
            check(pressed == min(2, len(exp_tags)), f"the chosen tags show as selected ({pressed})")
            await b.shot("reports_week_full", full=True)

        await b.js("document.getElementById('reportsPrev').click()")
        await asyncio.sleep(0.8)
        lab = await b.js("[document.getElementById('reportsRangeLabel').textContent, document.getElementById('reportsNext').disabled, document.getElementById('reportsFrom').value]")
        check(lab[2] == prev_mon.isoformat() and not lab[1], f"previous week, next enabled ({lab})")
        await b.js("document.getElementById('reportsPrev').click()")
        await asyncio.sleep(0.8)
        lab = await b.js("document.getElementById('reportsFrom').value")
        check(lab == old_mon.isoformat(), f"two weeks back ({lab})")
        if STAGE >= 2:
            s2 = await b.js(STATS_JS)
            check(s2["stats"][0] == ["3h 30m", "tiempo total"] and s2["stats"][2][0] == "3 de 7",
                  f"two weeks back: breaks excluded, 3 of 7 days ({s2['stats']})")
            check(s2["stats"][1][0] == "30m", f"average over the 7 days ({s2['stats'][1]})")
        if STAGE >= 4:
            heat = await b.js("""(() => {
                const card = [...document.querySelectorAll('.report-card')].find(c => c.querySelector('.report-heat'));
                const cells = [...card.querySelectorAll('.heat-cell')];
                const lit = cells.map((c, i) => c.title ? [Math.floor(i / 24), i % 24, c.title] : null).filter(Boolean);
                return {lit, insight: card.querySelector('.report-note.strong').textContent,
                        source: [...document.querySelectorAll('.report-card')].find(c => c.querySelector('.report-stack'))
                            .querySelector('.report-legend').textContent};
            })()""")
            spots = [(d, h) for d, h, _ in heat["lit"]]
            check(spots == [(1, 10), (1, 11), (2, 13), (2, 14), (3, 16)],
                  f"heatmap: Tue 10-12, Wed 13:30-14:30 split in two hours, Thu 16 ({spots})")
            wed = [t for d, h, t in heat["lit"] if d == 2]
            check(all(t.endswith(": 30m") for t in wed), f"the crossing session splits 30m + 30m ({wed})")
            check(heat["insight"] == "Tu mejor franja: de 10:00 a 12:00. El día que más rindes: el martes.",
                  f"best slot and day ({heat['insight']})")
            check("Cronómetro · 1h 0m (29%)" in heat["source"] and "Registrado a mano · 2h 30m (71%)" in heat["source"],
                  f"stopwatch vs manual ({heat['source']})")
            await b.shot("reports_prev", full=True)

        await b.js("document.querySelector('[data-range=month]').click()")
        await asyncio.sleep(0.4)
        lab = await b.js("[document.getElementById('reportsRangeLabel').textContent, document.getElementById('reportsFrom').value, document.getElementById('reportsTo').value]")
        check(lab[0].lower().endswith(str(today.year)) and lab[1] == today.replace(day=1).isoformat(), f"this month ({lab})")
        await b.js("document.getElementById('reportsPrev').click()")
        await asyncio.sleep(0.4)
        lab = await b.js("document.getElementById('reportsFrom').value")
        first_prev = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        check(lab == first_prev.isoformat(), f"previous month ({lab})")

        await b.js("document.querySelector('[data-range=custom]').click()")
        await asyncio.sleep(0.3)
        vis = await b.js("!document.getElementById('reportsCustom').classList.contains('hidden')")
        await b.js("""(() => { const f = document.getElementById('reportsFrom'), t = document.getElementById('reportsTo');
            f.value = '2026-09-10'; t.value = '2026-09-01'; t.dispatchEvent(new Event('change')); })()""")
        await asyncio.sleep(0.4)
        lab = await b.js("[document.getElementById('reportsRangeLabel').textContent, document.getElementById('reportsFrom').value, document.getElementById('reportsTo').value]")
        check(vis and lab[1:] == ["2026-09-01", "2026-09-10"], f"custom range, swapped if reversed ({lab})")
        await b.js("document.getElementById('reportsPrev').click()")
        await asyncio.sleep(0.3)
        lab = await b.js("[document.getElementById('reportsFrom').value, document.getElementById('reportsTo').value]")
        check(lab == ["2026-08-22", "2026-08-31"], f"custom range shifts by its length ({lab})")
        await b.js("document.querySelector('[data-range=week]').click()")
        await asyncio.sleep(0.3)

        # keyboard: from Reportes, ArrowRight wraps to Calendario
        await b.js("document.getElementById('tabReports').focus(); document.getElementById('tabReports').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}))")
        await asyncio.sleep(0.4)
        check(await b.js("currentViewIndex") == 0, "ArrowRight on Reportes wraps to Calendario")
        await b.js("document.getElementById('tabCalendar').dispatchEvent(new KeyboardEvent('keydown', {key: 'End', bubbles: true}))")
        await asyncio.sleep(0.4)
        check(await b.js("currentViewIndex") == 2, "End goes to Reportes")

        # a hidden view (module off) leaves the other two, by id, with a half-width indicator
        await b.js("setViewVisible('calendar', false)")
        await asyncio.sleep(0.4)
        st = await b.js("""({id: currentViewId, index: currentViewIndex,
            tabs: [...document.querySelectorAll('.tab-btn')].filter(t => t.offsetWidth > 0).map(t => t.id),
            ind: Math.round(document.querySelector('.tab-indicator').getBoundingClientRect().width),
            tabW: Math.round(document.getElementById('tabReports').getBoundingClientRect().width),
            sectionShown: document.getElementById('viewReports').getBoundingClientRect().left >= 0})""")
        check(st["id"] == "reports" and st["index"] == 1 and st["tabs"] == ["tabProjects", "tabReports"]
              and abs(st["ind"] - st["tabW"]) <= 2 and st["sectionShown"],
              f"hiding Calendario keeps Reportes, now second of two ({st})")
        await b.js("document.getElementById('tabReports').dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}))")
        await asyncio.sleep(0.4)
        check(await b.js("currentViewId") == "projects", "ArrowRight wraps over the visible tabs only")
        await b.js("setViewVisible('calendar', true); goToView('reports', {animate: false})")
        await asyncio.sleep(0.4)
        st = await b.js("({id: currentViewId, index: currentViewIndex, n: visibleViews().length})")
        check(st == {"id": "reports", "index": 2, "n": 3}, f"showing it again restores the three tabs ({st})")

        # mobile: swipe through the three views
        # Start the swipe test on Calendario: the last tab is remembered on reload
        await b.js("document.getElementById('tabCalendar').click()")
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)
        tabs_fit = await b.js("document.documentElement.scrollWidth")
        await swipe(b, 330, 60)
        v1 = await b.js("currentViewIndex")
        await swipe(b, 330, 60)
        v2 = await b.js("currentViewIndex")
        await swipe(b, 330, 60)
        v3 = await b.js("currentViewIndex")
        check((v1, v2, v3) == (1, 2, 2), f"swipe left: Calendario → Tableros → Reportes, stops at the end ({v1},{v2},{v3})")
        check(tabs_fit <= 390, f"three tabs fit on a phone ({tabs_fit}px)")
        await swipe(b, 60, 330)
        check(await b.js("currentViewIndex") == 1, "swipe right goes back to Tableros")
        await b.js("document.getElementById('tabReports').click()")
        await asyncio.sleep(0.8)
        w = await b.js("document.documentElement.scrollWidth")
        check(w <= 390, f"reports view has no horizontal overflow on a phone ({w}px)")
        await b.shot("reports_mobile", full=False)
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_reports():
    asyncio.run(main())
