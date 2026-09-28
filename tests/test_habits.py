"""Hábitos: definiciones, días marcados, racha (solo en el backend) y reporte."""
import random
from datetime import date, timedelta

from backend.routers.habits import SHIELD_EVERY, _walk_streak


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
