"""Hábitos: definiciones, días marcados, racha (solo en el backend) y reporte."""
import random
from datetime import date, timedelta

from backend.routers.habits import _best_streak, _current_streak


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


def test_streak_rule_matches_the_reference():
    rng = random.Random(7)
    today = date(2026, 9, 23)
    for _ in range(500):
        rest = set(rng.sample(range(7), rng.randint(0, 3)))
        density = rng.random()
        done = {today - timedelta(days=i) for i in range(60) if rng.random() < density}
        cutoff = today - timedelta(days=400)
        assert _current_streak(done, rest, today, cutoff) == reference_streak(done, rest, today, cutoff)


def test_best_streak():
    today = date(2026, 9, 23)
    done = {date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8)}   # 1 = martes; 5 y 6 son fin de semana
    assert _best_streak(done, {5, 6}, today) == 6           # el descanso no corta
    assert _best_streak(done, set(), today) == 4            # sin descanso, el fin de semana corta
    assert _best_streak({today}, set(), today) == 1
    assert _best_streak(set(), set(), today) == 0


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
