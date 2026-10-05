"""Cuentas (BACKLOG 26, parte sin correo): cambiar la contraseña e irse."""
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select as sa_select
from sqlmodel import Session, SQLModel, select

from backend.accounts import GRACE_DAYS
from backend.database import engine
from backend.models import User, utc_now_naive
from conftest import PASSWORD

NEW = "otra-clave-123"


def user_row(session, email):
    return session.exec(select(User).where(User.email == email)).first()


def rows_of(user_id):
    """Cuántas filas tiene la cuenta en cada tabla con user_id."""
    with Session(engine) as session:
        return {table.name: session.execute(sa_select(func.count()).select_from(table)
                                            .where(table.c.user_id == user_id)).scalar()
                for table in SQLModel.metadata.sorted_tables if "user_id" in table.columns}


def test_change_password(api):
    api.login("clave@test.com")
    old_token = api.token
    assert api.call("POST", "/api/auth/me/password", {"current_password": "mala", "new_password": NEW})[0] == 400
    assert api.call("POST", "/api/auth/me/password", {"current_password": PASSWORD, "new_password": PASSWORD})[0] == 400
    # Sin cerrar las otras sesiones: el token de antes sigue valiendo
    _, tok = api.call("POST", "/api/auth/me/password",
                      {"current_password": PASSWORD, "new_password": NEW, "logout_others": False}, expect=200)
    assert api.call("GET", "/api/auth/me")[0] == 200
    api.token = tok["access_token"]
    # Cerrándolas: el de antes ya no; el nuevo sí
    _, tok = api.call("POST", "/api/auth/me/password",
                      {"current_password": NEW, "new_password": PASSWORD + "x"}, expect=200)
    api.token = old_token
    assert api.call("GET", "/api/auth/me")[0] == 401
    api.token = tok["access_token"]
    assert api.call("GET", "/api/auth/me")[0] == 200
    # Y se entra con la nueva
    api.login("clave@test.com", PASSWORD + "x")
    assert api.token


def test_leave_for_a_while_and_come_back(api):
    api.login("irme@test.com")
    old_token = api.token
    assert api.call("POST", "/api/auth/me/delete", {"password": "mala", "mode": "later"})[0] == 400
    _, sched = api.call("POST", "/api/auth/me/delete",
                        {"password": PASSWORD, "mode": "later", "logout_others": False}, expect=200)
    days = (sched["delete_after"][:10])
    assert days == (utc_now_naive() + timedelta(days=GRACE_DAYS)).date().isoformat()
    assert sched["access_token"] is None
    _, me = api.call("GET", "/api/auth/me", expect=200)          # la sesión sigue
    assert me["delete_after"]
    # Entrar otra vez deja conservarla
    api.login("irme@test.com")
    _, me = api.call("POST", "/api/auth/me/keep", expect=200)
    assert me["delete_after"] is None
    # Irse cerrando las otras sesiones
    api.token = old_token
    _, sched = api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "later"}, expect=200)
    assert api.call("GET", "/api/auth/me")[0] == 401
    api.token = sched["access_token"]
    assert api.call("GET", "/api/auth/me", expect=200)[1]["delete_after"]


def test_delete_now_removes_everything(seeded):
    api, other = seeded["api"], seeded["other"]
    api.call("POST", "/api/reports", {"kind": "week",
                                      "period_start": (utc_now_naive().date() - timedelta(days=utc_now_naive().weekday())).isoformat()},
             expect=200)
    with Session(engine) as session:
        me = user_row(session, "yoshi@test.com")
        them = user_row(session, "otro@test.com")
        my_id, their_id = me.id, them.id
    before = rows_of(my_id)
    assert sum(before.values()) > 10                       # tenía de todo
    theirs_before = rows_of(their_id)

    assert api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "now"})[0] == 400
    assert api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "now", "confirm": "borrar"})[0] == 204
    assert api.call("GET", "/api/auth/me")[0] == 401
    assert sum(rows_of(my_id).values()) == 0, {t: n for t, n in rows_of(my_id).items() if n}
    with Session(engine) as session:
        assert session.get(User, my_id) is None
    # Lo de la otra cuenta, intacto
    assert rows_of(their_id) == theirs_before
    assert other.call("GET", "/api/tasks", expect=200)[1]["total"] == 1
    # Y el correo queda libre otra vez
    api.token = None
    assert api.call("POST", "/api/auth/register", {"email": "yoshi@test.com", "password": PASSWORD})[0] == 200


def test_wrong_passwords_count_for_the_login_limit(api):
    api.login("limite-clave@test.com")
    for _ in range(10):
        assert api.call("POST", "/api/auth/me/password", {"current_password": "mala", "new_password": NEW})[0] == 400
    assert api.call("POST", "/api/auth/me/password", {"current_password": PASSWORD, "new_password": NEW})[0] == 429


def test_purge_script_and_reports_skip(api, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import purge_accounts
    api.login("vence@test.com")
    api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "later"}, expect=200)
    api.login("todavia@test.com")
    api.call("POST", "/api/auth/me/delete", {"password": PASSWORD, "mode": "later"}, expect=200)
    with Session(engine) as session:
        due = user_row(session, "vence@test.com")
        due.delete_after = utc_now_naive() - timedelta(minutes=1)
        session.add(due)
        session.commit()
        due_id = due.id

    assert purge_accounts.main(["--dry-run"]) == 0
    assert f"would delete account {due_id}" in capsys.readouterr().out
    assert purge_accounts.main([]) == 0
    assert "1 account(s) deleted." in capsys.readouterr().out
    with Session(engine) as session:
        assert session.get(User, due_id) is None
        assert user_row(session, "todavia@test.com") is not None   # aún no vence

