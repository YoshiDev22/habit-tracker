"""Reportar un problema (1.27): POST /api/feedback, su límite diario y sus topes."""
from sqlmodel import Session, select

from backend.database import engine
from backend.models import Feedback, User
from backend.routers.feedback import FEEDBACK_DAILY_LIMIT

DETAILS = {"version": "v1.27.0", "view": "projects", "screen": "390×844",
           "user_agent": "Mozilla/5.0 (Test)", "errors": ["TypeError: x is undefined (board.js:12)"]}


def rows(email):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if user is None:
            return []
        return [(f.text, f.details, f.status) for f in
                session.exec(select(Feedback).where(Feedback.user_id == user.id).order_by(Feedback.id)).all()]


def test_a_problem_is_saved_with_its_details(api):
    api.login("reporta@test.com")
    _, saved = api.call("POST", "/api/feedback", {"text": "  El tablero no carga al abrirlo  ", "details": DETAILS},
                        expect=201)
    assert set(saved) == {"id", "created_at"}          # no devuelve nada más
    api.call("POST", "/api/feedback", {"text": "Sin detalles técnicos esta vez"}, expect=201)
    assert rows("reporta@test.com") == [("El tablero no carga al abrirlo", DETAILS, "open"),
                                        ("Sin detalles técnicos esta vez", None, "open")]


def test_only_known_details_get_in(api):
    api.login("detalles@test.com")
    url = "/api/feedback"
    text = "Algo falló al guardar"
    for bad in ({"token": "eyJ..."}, {"version": 5}, {"errors": "boom"}, {"errors": [1]},
                {"errors": ["x"] * 11}, {"errors": ["x" * 301]}, {"user_agent": "x" * 301},
                {"view": "x" * 21}):
        assert api.call("POST", url, {"text": text, "details": bad})[0] == 422, bad
    api.call("POST", url, {"text": text, "details": {"errors": ["x" * 300] * 10, "user_agent": "x" * 300}},
             expect=201)
    assert rows("detalles@test.com")[0][1] == {"errors": ["x" * 300] * 10, "user_agent": "x" * 300}


def test_five_a_day_then_429(api):
    api.login("muchos@test.com")
    for i in range(FEEDBACK_DAILY_LIMIT):
        api.call("POST", "/api/feedback", {"text": f"Problema número {i}"}, expect=201)
    status, body = api.call("POST", "/api/feedback", {"text": "Uno más de la cuenta"})
    assert status == 429 and "mañana" in body["detail"]
    assert len(rows("muchos@test.com")) == FEEDBACK_DAILY_LIMIT
    # El límite es de cada cuenta
    api.login("otra-cuenta@test.com")
    api.call("POST", "/api/feedback", {"text": "Mi primer reporte"}, expect=201)


def test_needs_an_account_and_leaves_with_it(api):
    api.token = None
    assert api.call("POST", "/api/feedback", {"text": "Sin cuenta no se puede"})[0] == 401
    api.login("se-va@test.com")
    api.call("POST", "/api/feedback", {"text": "Antes de irme, esto falló"}, expect=201)
    api.call("POST", "/api/auth/me/delete", {"password": "secret123", "mode": "now", "confirm": "BORRAR"},
             expect=204)
    assert rows("se-va@test.com") == []
    with Session(engine) as session:
        assert session.exec(select(Feedback)).all() == []
