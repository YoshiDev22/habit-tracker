"""Hábitos: definiciones, días marcados, racha (solo en el backend) y reporte."""
import random
from datetime import date, timedelta

from backend.routers.habits import MIN_HABITS_FOR_DONE_DAY, SHIELD_EVERY, _is_done_day, _walk_streak


def test_definitions_are_validated(api):
    api.login("valid@test.com")
    url = "/api/habits/definitions"
    assert api.call("POST", url, {"key": "a", "label": "A", "color": "rojo; drop table"})[0] == 422
    assert api.call("POST", url, {"key": "b", "label": "x" * 5000})[0] == 422
    assert api.call("POST", url, {"key": "", "label": "Vacía"})[0] == 422
    assert api.call("POST", url, {"key": "c", "label": "C", "icon": "x" * 50})[0] == 422
    _, h = api.call("POST", url, {"key": "familia", "label": "Familia", "icon": "👨‍👩‍👧‍👦", "color": "#3498db"}, expect=201)
    api.call("POST", url, {"key": "sincolor", "label": "Sin color", "icon": "", "color": None}, expect=201)
    assert api.call("POST", url, {"key": "familia", "label": "Otra"})[0] == 409
    assert api.call("PATCH", f"{url}/{h['id']}", {"color": "blue"})[0] == 422
    assert api.call("PATCH", f"{url}/{h['id']}", {"label": ""})[0] == 422
    # El color vive en la cuenta: se guarda y se lee de vuelta
    _, r = api.call("PATCH", f"{url}/{h['id']}", {"color": "#27ae60", "icon": "📚", "is_active": False}, expect=200)
    assert r["color"] == "#27ae60" and r["is_active"] is False


def test_mark_days_and_streak(api):
    api.login("flow@test.com")
    today = date.today()
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    for i in (2, 1, 0):
        api.call("POST", "/api/habits", {"date": (today - timedelta(days=i)).isoformat(), "habits": {"gym": True}}, expect=200)
    _, h = api.call("GET", f"/api/habits?today={today}", expect=200)
    assert any(e["date"] == today.isoformat() and e["habits_data"]["gym"] for e in h["entries"])
    assert h["streak"] == 3
    assert api.call("GET", f"/api/habits/streak?today={today}", expect=200)[1]["streak"] == 3


def test_mark_one_habit_keeps_the_rest_of_the_day(api):
    api.login("mark@test.com")
    today = date.today().isoformat()
    for key in ("gym", "lectura", "musica"):
        api.call("POST", "/api/habits/definitions", {"key": key, "label": key}, expect=201)
    day = lambda: next((e["habits_data"] for e in api.call("GET", f"/api/habits?today={today}", expect=200)[1]["entries"]
                        if e["date"] == today), None)
    # Sin entrada todavía: la crea con ese solo hábito
    _, r = api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": "gym", "done": True}, expect=200)
    assert r["habits_data"] == {"gym": True} and day() == {"gym": True}
    api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": "lectura", "done": True}, expect=200)
    # Desmarcar uno deja los demás, aunque sea el último visible
    api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": "gym", "done": False}, expect=200)
    assert day() == {"lectura": True}
    # Un hábito oculto también se puede marcar (es suyo)
    _, h = api.call("GET", "/api/habits/definitions", expect=200)
    musica = next(x for x in h["habits"] if x["key"] == "musica")
    api.call("PATCH", f"/api/habits/definitions/{musica['id']}", {"is_active": False}, expect=200)
    api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": "musica", "done": True}, expect=200)
    assert day() == {"lectura": True, "musica": True}
    # Un hábito que no existe: 404, y el día queda igual
    assert api.call("PATCH", f"/api/habits/day/{today}", {"habit_key": "nada", "done": True})[0] == 404
    assert day() == {"lectura": True, "musica": True}


def reference_streak(done, rest, today, cutoff):
    """La regla escrita en calculate_streak, contada a mano día por día."""
    streak, day = 0, today
    while day >= cutoff:
        if day in done:
            streak += 1
        elif day == today or day.weekday() in rest:
            pass
        else:
            break
        day -= timedelta(days=1)
    return streak


def longest_run(done):
    """Días hechos seguidos más largos, sin contar descansos ni protectores."""
    best = run = 0
    for day in sorted(done):
        run = run + 1 if day - timedelta(days=1) in done else 1
        best = max(best, run)
    return best


def test_streak_rule_matches_the_reference():
    """Mientras nunca se junten 7 días hechos (sin protectores), la regla es la
    de siempre: la del calendario, contada hacia atrás."""
    rng = random.Random(7)
    today = date(2026, 9, 23)
    checked = 0
    for _ in range(2000):
        rest = set(rng.sample(range(7), rng.randint(0, 3)))
        density = rng.random()
        done = {today - timedelta(days=i) for i in range(60) if rng.random() < density}
        walk = _walk_streak(done, rest, today)
        if walk.protected or walk.shields:
            continue
        cutoff = today - timedelta(days=400)
        assert walk.current == reference_streak(done, rest, today, cutoff)
        checked += 1
    assert checked > 300


def test_best_streak():
    today = date(2026, 9, 23)
    done = {date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8)}   # 1 = martes; 5 y 6 son fin de semana
    assert _walk_streak(done, {5, 6}, today).best == 6      # el descanso no corta
    assert _walk_streak(done, set(), today).best == 4       # sin descanso, el fin de semana corta
    assert _walk_streak({today}, set(), today).best == 1
    assert _walk_streak(set(), set(), today).best == 0


def days(today, *offsets):
    return {today - timedelta(days=i) for i in offsets}


def test_shields_are_earned_every_seven_days_up_to_two():
    today = date(2026, 9, 23)
    assert _walk_streak(days(today, *range(1, 7)), set(), today).shields == 0      # 6 días
    w = _walk_streak(days(today, *range(1, 8)), set(), today)                       # 7 días
    assert (w.current, w.shields, w.progress) == (7, 1, 0)
    w = _walk_streak(days(today, *range(1, 30)), set(), today)                      # 29 días
    assert w.shields == 2 and w.current == 29


def test_a_shield_covers_a_missed_day_and_the_streak_goes_on():
    today = date(2026, 9, 23)
    # 7 días, uno sin nada (hace 3), y 2 más: el protector lo cubre
    done = days(today, *range(4, 11)) | days(today, 2, 1)
    w = _walk_streak(done, set(), today)
    assert w.protected == [today - timedelta(days=3)]
    assert (w.current, w.shields, w.best) == (9, 0, 9)
    # Dos días seguidos sin nada con un solo protector: se corta
    done = days(today, *range(5, 12)) | days(today, 2, 1)
    w = _walk_streak(done, set(), today)
    assert w.current == 2 and w.best == 7 and w.shields == 0
    # Con dos protectores, dos días seguidos se cubren
    done = days(today, *range(5, 19)) | days(today, 2, 1)
    w = _walk_streak(done, set(), today)
    assert w.current == 16 and len(w.protected) == 2


def test_rest_days_and_today_do_not_spend_shields():
    today = date(2026, 9, 23)                                # miércoles
    done = days(today, *range(1, 8))
    w = _walk_streak(done, set(), today)                     # hoy sin nada: no gasta
    assert w.shields == 1 and not w.protected
    done = days(today, *range(3, 10)) | days(today, 1)       # hace 2 = lunes, de descanso
    w = _walk_streak(done, {0}, today)
    assert w.shields == 1 and not w.protected and w.current == 8


def test_backfilling_a_forgotten_day_gives_the_shield_back():
    today = date(2026, 9, 23)
    done = days(today, *range(2, 9))
    w = _walk_streak(done, set(), today)
    assert w.protected == [today - timedelta(days=1)] and w.shields == 0
    w = _walk_streak(done | days(today, 1), set(), today)
    assert not w.protected and w.shields == 1 and w.current == 8


def test_missed_yesterday():
    today = date(2026, 9, 23)                                # miércoles; ayer = martes (1)
    yesterday = today - timedelta(days=1)
    # Ayer hecho: nada que preguntar
    assert _walk_streak(days(today, 1, 2), set(), today).missed_yesterday is None
    # Había racha y ayer quedó vacío: se cortó
    w = _walk_streak(days(today, 2, 3), set(), today)
    assert w.missed_yesterday == {"date": yesterday, "streak": 2, "shielded": False}
    # Lo cubrió un protector
    w = _walk_streak(days(today, *range(2, 9)), set(), today)
    assert w.missed_yesterday == {"date": yesterday, "streak": 7, "shielded": True}
    # Ayer era de descanso: no se pregunta
    assert _walk_streak(days(today, 2, 3), {1}, today).missed_yesterday is None
    # Sin racha antes de ayer (hace días que no se anota): tampoco
    assert _walk_streak(days(today, 10), set(), today).missed_yesterday is None


def test_streak_endpoints_carry_the_shields(api):
    api.login("shields@test.com")
    today = date.today()
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    for i in range(2, 2 + SHIELD_EVERY):
        api.call("POST", "/api/habits", {"date": (today - timedelta(days=i)).isoformat(), "habits": {"gym": True}}, expect=200)
    yesterday = (today - timedelta(days=1)).isoformat()
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    assert st["streak"] == SHIELD_EVERY and st["streak_shields"] == 0
    assert st["protected_days"] == [yesterday]
    assert st["missed_yesterday"] == {"date": yesterday, "streak": SHIELD_EVERY, "shielded": True}
    assert st["shield_next_in"] == SHIELD_EVERY
    _, h = api.call("GET", f"/api/habits?today={today}", expect=200)
    assert {k: h[k] for k in st} == st
    # Anotar ayer lo devuelve
    api.call("POST", "/api/habits", {"date": yesterday, "habits": {"gym": True}}, expect=200)
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    assert st["streak"] == SHIELD_EVERY + 1 and st["streak_shields"] == 1
    assert st["protected_days"] == [] and st["missed_yesterday"] is None
    assert st["shield_next_in"] == SHIELD_EVERY - 1
    _, hr = api.call("GET", f"/api/habits/report?date_from={today}&date_to={today}&today={today}", expect=200)
    assert hr["streak_shields"] == 1


def test_done_day_needs_one_habit_hidden_or_not():
    assert MIN_HABITS_FOR_DONE_DAY == 1
    assert _is_done_day({"gym": True})
    assert _is_done_day({"gym": False, "oculto": True})
    assert not _is_done_day({"gym": False})
    assert not _is_done_day({}) and not _is_done_day(None)


def test_rest_day_with_a_habit_counts_normally():
    today = date(2026, 9, 23)                                # miércoles; hace 2 = lunes
    rest = {0}
    done = days(today, 1, 3)
    assert _walk_streak(done, rest, today).current == 2     # lunes vacío: congela
    assert _walk_streak(done | days(today, 2), rest, today).current == 3   # lunes hecho: suma


def test_today_unmarked_does_not_break_the_streak():
    today = date(2026, 9, 23)
    w = _walk_streak(days(today, 1, 2, 3), set(), today)
    assert w.current == 3 and not w.protected and w.missed_yesterday is None


def test_best_streak_differs_from_the_current_one():
    today = date(2026, 9, 23)
    done = days(today, *range(20, 25)) | days(today, 1, 2)   # 5 seguidos hace tiempo, luego 2
    w = _walk_streak(done, set(), today)
    assert (w.current, w.best) == (2, 5)


def test_a_day_with_only_a_hidden_habit_keeps_the_streak(api):
    api.login("hidden-streak@test.com")
    today = date.today()
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    _, lectura = api.call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura"}, expect=201)
    for i, key in ((3, "gym"), (2, "lectura"), (1, "gym")):
        api.call("PATCH", f"/api/habits/day/{today - timedelta(days=i)}", {"habit_key": key, "done": True}, expect=200)
    api.call("PATCH", f"/api/habits/definitions/{lectura['id']}", {"is_active": False}, expect=200)
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    assert st["streak"] == 3 and st["best_streak"] == 3 and st["protected_days"] == []
    _, h = api.call("GET", f"/api/habits?today={today}", expect=200)
    assert h["best_streak"] == 3


def test_new_habits_go_last_and_keep_everyone_in_place(api):
    api.login("order@test.com")
    url = "/api/habits/definitions"
    _, a = api.call("POST", url, {"key": "a", "label": "A"}, expect=201)
    _, b = api.call("POST", url, {"key": "b", "label": "B"}, expect=201)
    api.call("PATCH", f"{url}/{a['id']}", {"is_active": False}, expect=200)
    _, c = api.call("POST", url, {"key": "c", "label": "C"}, expect=201)
    assert (a["order"], b["order"], c["order"]) == (0, 1, 2)   # c va detrás del oculto también
    _, all_habits = api.call("GET", f"{url}?include_inactive=true", expect=200)
    assert [h["key"] for h in all_habits["habits"]] == ["a", "b", "c"]
    # Restaurar lo devuelve a su lugar
    api.call("PATCH", f"{url}/{a['id']}", {"is_active": True}, expect=200)
    assert [h["key"] for h in api.call("GET", url, expect=200)[1]["habits"]] == ["a", "b", "c"]
    # Un order explícito se respeta
    _, d = api.call("POST", url, {"key": "d", "label": "D", "order": 10}, expect=201)
    assert d["order"] == 10


def test_month_habits_include_hidden_ones_with_records(api):
    api.login("month@test.com")
    url = "/api/habits/definitions"
    today = date.today()
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    for key in ("gym", "lectura", "musica", "dieta"):
        api.call("POST", url, {"key": key, "label": key.title()}, expect=201)
    ids = {h["key"]: h["id"] for h in api.call("GET", url, expect=200)[1]["habits"]}
    api.call("PATCH", f"/api/habits/day/{last_month}", {"habit_key": "lectura", "done": True}, expect=200)
    api.call("PATCH", f"/api/habits/day/{last_month + timedelta(days=1)}", {"habit_key": "musica", "done": True}, expect=200)
    api.call("PATCH", f"/api/habits/day/{last_month + timedelta(days=1)}", {"habit_key": "musica", "done": False}, expect=200)
    for key in ("lectura", "musica"):
        api.call("PATCH", f"{url}/{ids[key]}", {"is_active": False}, expect=200)

    def shown(month_start):
        _, r = api.call("GET", f"/api/habits/month-habits?year={month_start.year}&month={month_start.month}", expect=200)
        return [(h["key"], h["is_active"]) for h in r["habits"]]

    # El mes pasado: Lectura oculta sigue en su lugar; Música (desmarcada) no tiene registros
    assert shown(last_month) == [("gym", True), ("lectura", False), ("dieta", True)]
    # Este mes: solo los activos
    assert shown(this_month) == [("gym", True), ("dieta", True)]
    assert api.call("GET", "/api/habits/month-habits?year=2026&month=13")[0] == 422


def test_delete_impact(api):
    api.login("impact@test.com")
    today = date.today()
    url = "/api/habits/definitions"
    api.call("POST", url, {"key": "gym", "label": "Gym"}, expect=201)
    _, lectura = api.call("POST", url, {"key": "lectura", "label": "Lectura"}, expect=201)
    for i, key in ((3, "gym"), (2, "lectura"), (1, "gym"), (1, "lectura")):
        api.call("PATCH", f"/api/habits/day/{today - timedelta(days=i)}", {"habit_key": key, "done": True}, expect=200)
    _, imp = api.call("GET", f"{url}/{lectura['id']}/delete-impact?today={today}", expect=200)
    # Sin Lectura, hace 2 días queda vacío y corta la racha (aún no hay protectores)
    assert imp == {"records": 2, "streak_before": 3, "streak_after": 1, "best_before": 3, "best_after": 1}
    # Solo calcula: no borra nada
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    assert st["streak"] == 3
    # Después de borrar de verdad, la racha es la que anunció
    api.call("DELETE", "/api/habits/delete-habit", {"habit_key": "lectura"}, expect=200)
    api.call("DELETE", f"{url}/{lectura['id']}", expect=204)
    assert api.call("GET", f"/api/habits/streak?today={today}", expect=200)[1]["streak"] == imp["streak_after"]


def test_each_habit_carries_its_own_streak(api):
    api.login("per-habit@test.com")
    today = date.today()
    for key in ("gym", "lectura", "musica"):
        api.call("POST", "/api/habits/definitions", {"key": key, "label": key}, expect=201)
    for i, key in ((3, "gym"), (2, "gym"), (1, "gym"), (1, "lectura"), (10, "musica")):
        api.call("PATCH", f"/api/habits/day/{today - timedelta(days=i)}", {"habit_key": key, "done": True}, expect=200)
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    # Música se cortó hace días: no aparece; cada uno con la regla de siempre
    assert st["habit_streaks"] == {"gym": 3, "lectura": 1}
    assert api.call("GET", f"/api/habits?today={today}", expect=200)[1]["habit_streaks"] == st["habit_streaks"]


def test_habit_report(api):
    api.login("report@test.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    prev_mon = monday - timedelta(days=7)
    api.call("PATCH", "/api/auth/me", {"rest_days": [5, 6]}, expect=200)
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "color": "#e74c3c"}, expect=201)
    api.call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura", "order": 1}, expect=201)
    day = prev_mon
    while day <= today:
        if day.weekday() < 5:
            api.call("POST", "/api/habits", {"date": day.isoformat(), "habits": {"gym": True, "lectura": day == monday}}, expect=200)
        day += timedelta(days=1)

    elapsed = today.weekday() + 1
    target = sum(1 for i in range(elapsed) if (monday + timedelta(days=i)).weekday() < 5)
    q = f"date_from={monday}&date_to={monday + timedelta(days=6)}&today={today}"
    _, hr = api.call("GET", f"/api/habits/report?{q}", expect=200)
    gym = next(h for h in hr["habits"] if h["key"] == "gym")
    lec = next(h for h in hr["habits"] if h["key"] == "lectura")
    assert hr["days_elapsed"] == elapsed and hr["days_elapsed"] - hr["rest_days_elapsed"] == target
    assert hr["active_days"] == target
    assert gym["days_done"] == target and gym["current_streak"] == gym["best_streak"] == 5 + target
    assert lec["days_done"] == 1 and lec["best_streak"] == 1
    assert hr["streak"] == api.call("GET", f"/api/habits/streak?today={today}", expect=200)[1]["streak"]
    assert api.call("GET", f"/api/habits/report?date_from={today}&date_to={monday - timedelta(days=1)}")[0] == 422
