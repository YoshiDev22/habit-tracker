"""users.last_seen_at (1.27): la última actividad, como mucho una escritura por hora."""
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import event
from sqlmodel import Session, select

from backend.auth import LAST_SEEN_EVERY
from backend.database import engine
from backend.models import User, utc_now_naive


@contextmanager
def user_updates():
    """Las sentencias UPDATE sobre users que llegan a la base mientras dura el bloque."""
    seen = []

    def listen(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE USERS"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", listen)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", listen)


def last_seen(email):
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).one().last_seen_at


def set_last_seen(email, value):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).one()
        user.last_seen_at = value
        session.add(user)
        session.commit()


def test_marks_activity_at_most_once_an_hour(api):
    api.login("activa@test.com")
    set_last_seen("activa@test.com", None)          # como una cuenta de antes de la 1.27
    before = utc_now_naive()
    with user_updates() as updates:
        api.call("GET", "/api/auth/me", expect=200)
    first = last_seen("activa@test.com")
    assert len(updates) == 1 and first is not None and first >= before

    # Varias peticiones seguidas: ni una escritura más
    with user_updates() as updates:
        for path in ("/api/auth/me", "/api/projects", "/api/notices", "/api/auth/me"):
            api.call("GET", path, expect=200)
    assert updates == [] and last_seen("activa@test.com") == first

    # Pasada la hora, la siguiente la vuelve a anotar
    set_last_seen("activa@test.com", first - LAST_SEEN_EVERY - timedelta(seconds=1))
    with user_updates() as updates:
        api.call("GET", "/api/auth/me", expect=200)
    assert len(updates) == 1 and last_seen("activa@test.com") >= before


def test_a_rejected_token_marks_nothing(api):
    api.login("rechazada@test.com")
    set_last_seen("rechazada@test.com", None)
    good = api.token
    api.token = good[:-3] + ("aaa" if not good.endswith("aaa") else "bbb")
    with user_updates() as updates:
        assert api.call("GET", "/api/auth/me")[0] == 401
    assert updates == [] and last_seen("rechazada@test.com") is None


def test_a_revoked_session_marks_nothing(api):
    """Un token de antes de cerrar las sesiones (otra versión) da 401 y no cuenta como actividad."""
    api.login("revocada@test.com")
    set_last_seen("revocada@test.com", None)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "revocada@test.com")).one()
        user.token_version = (user.token_version or 0) + 1
        session.add(user)
        session.commit()
    with user_updates() as updates:
        assert api.call("GET", "/api/auth/me")[0] == 401
    assert updates == [] and last_seen("revocada@test.com") is None
