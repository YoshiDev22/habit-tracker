"""Pausa por vacaciones (Calendario v2, fase 6): los días en pausa congelan la racha,
se programan hoy o hacia adelante, duran hasta 30 días y no se cruzan."""
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.models import StreakPause, User
from backend.routers.habits import _walk_streak


def insert_pause(email, start, end):
    """Una pausa que ya empezó: la API no deja crearla hacia atrás, así que va directa."""
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).one()
        pause = StreakPause(user_id=user.id, start_date=start, end_date=end)
        session.add(pause)
        session.commit()
        return pause.id


def test_paused_days_freeze_the_streak_like_rest_days():
    today = date(2026, 9, 23)
    done = {today - timedelta(days=i) for i in (5, 6, 7)}
    paused = {today - timedelta(days=i) for i in (1, 2, 3, 4)}
    w = _walk_streak(done, set(), today, paused)
    assert (w.current, w.shields, w.protected, w.missed_yesterday) == (3, 0, [], None)
    # Sin la pausa, esos cuatro días la cortan
    assert _walk_streak(done, set(), today).current == 0
    # Un hábito marcado en pausa cuenta normal
    assert _walk_streak(done | {today - timedelta(days=2)}, set(), today, paused).current == 4


def test_schedule_list_and_cancel(api):
    api.login("pausa@test.com")
    today = date.today()
    url = f"/api/habits/pauses?today={today}"
    _, p = api.call("POST", url, {"start_date": str(today + timedelta(days=3)), "end_date": str(today + timedelta(days=9))}, expect=201)
    _, lst = api.call("GET", "/api/habits/pauses", expect=200)
    assert [(x["start_date"], x["end_date"]) for x in lst["pauses"]] == [(p["start_date"], p["end_date"])]
    # Sus días viajan con la racha, para el calendario
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    assert str(today + timedelta(days=3)) in st["paused_days"] and len(st["paused_days"]) == 7
    # Cancelar una que no ha empezado la borra
    api.call("DELETE", f"/api/habits/pauses/{p['id']}?today={today}", expect=204)
    assert api.call("GET", "/api/habits/pauses", expect=200)[1]["pauses"] == []


def test_rules_when_scheduling(api):
    api.login("reglas-pausa@test.com")
    today = date.today()
    url = f"/api/habits/pauses?today={today}"
    body = lambda a, b: {"start_date": str(today + timedelta(days=a)), "end_date": str(today + timedelta(days=b))}
    # Hacia atrás no: para eso están los escudos
    status, err = api.call("POST", url, body(-1, 3))
    assert status == 422 and "escudos" in err["detail"]
    # Termina antes de empezar, o dura más de 30 días
    assert api.call("POST", url, body(5, 2))[0] == 422
    assert api.call("POST", url, body(0, 30))[0] == 422
    api.call("POST", url, body(0, 29), expect=201)             # 30 días justos, desde hoy
    # No se cruzan
    status, err = api.call("POST", url, body(29, 35))
    assert status == 409 and "Se cruza" in err["detail"]
    api.call("POST", url, body(30, 35), expect=201)


def test_a_started_pause_can_end_early_and_a_finished_one_stays(api):
    api.login("en-curso@test.com")
    today = date.today()
    ongoing = insert_pause("en-curso@test.com", today - timedelta(days=3), today + timedelta(days=3))
    api.call("DELETE", f"/api/habits/pauses/{ongoing}?today={today}", expect=204)
    _, lst = api.call("GET", "/api/habits/pauses", expect=200)
    assert [(x["start_date"], x["end_date"]) for x in lst["pauses"]] == [
        (str(today - timedelta(days=3)), str(today - timedelta(days=1)))]   # queda hasta ayer
    status, err = api.call("DELETE", f"/api/habits/pauses/{ongoing}?today={today}")
    assert status == 409 and "historial" in err["detail"]


def test_vacation_keeps_the_streak_in_the_api_and_the_report(api):
    api.login("vacaciones@test.com")
    today = date.today()
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym"}, expect=201)
    for i in (5, 6, 7):
        api.call("PATCH", f"/api/habits/day/{today - timedelta(days=i)}", {"habit_key": "gym", "done": True}, expect=200)
    insert_pause("vacaciones@test.com", today - timedelta(days=4), today - timedelta(days=1))
    _, st = api.call("GET", f"/api/habits/streak?today={today}", expect=200)
    assert st["streak"] == 3 and st["protected_days"] == [] and st["missed_yesterday"] is None
    assert st["habit_streaks"] == {"gym": 3}
    frm = today - timedelta(days=7)
    _, hr = api.call("GET", f"/api/habits/report?date_from={frm}&date_to={today}&today={today}", expect=200)
    assert hr["days_elapsed"] == 8 and hr["paused_days_elapsed"] == 4 and hr["streak"] == 3
