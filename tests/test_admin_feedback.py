"""Problemas reportados desde el panel (1.27, Fase 2, paso 5): estado, notas y el aviso
a quien lo reportó al cerrarlo."""
import json
from datetime import date

from test_admin_actions import PANEL
from test_admin_auth import admin, token  # noqa: F401

TODAY = date.today().isoformat()


def update(admin, feedback_id, body):
    return admin.client.put(f"/api/feedback/{feedback_id}", content=json.dumps(body),
                            headers={"Cf-Access-Jwt-Assertion": token(), "Origin": PANEL,
                                     "Content-Type": "application/json"})


def closed_notices(api):
    data = api.call("GET", f"/api/notices?today={TODAY}", expect=200)[1]
    return [n for n in data["notices"] if n["kind"] == "feedback_closed"]


def report(api, text="El tablero no carga al abrirlo"):
    return api.call("POST", "/api/feedback", {"text": text}, expect=201)[1]["id"]


def test_close_tells_the_person_once_with_the_note_for_them(admin, api):
    api.login("reporto@test.com")
    fid = report(api)
    r = update(admin, fid, {"status": "reviewed", "admin_note": "Pasa con Chrome 120: revisar loadBoard"})
    assert r.status_code == 200 and r.json()["status"] == "reviewed"
    assert closed_notices(api) == []                                   # revisado no avisa

    r = update(admin, fid, {"status": "closed", "user_note": "Ya quedó: actualiza la página."})
    assert r.status_code == 200
    [notice] = closed_notices(api)
    assert notice["title"].startswith("Revisamos el problema que reportaste el ")
    assert notice["detail"] == "Ya quedó: actualiza la página." and not notice["read"]
    assert "Chrome 120" not in json.dumps(notice, ensure_ascii=False)   # la nota interna no sale
    # Reabrir y volver a cerrar no repite el aviso
    update(admin, fid, {"status": "open"})
    update(admin, fid, {"status": "closed"})
    assert len(closed_notices(api)) == 1

    listed = admin("/api/feedback", jwt_token=token()).json()["feedback"][0]
    assert (listed["status"], listed["admin_note"], listed["user_note"]) == \
        ("closed", "Pasa con Chrome 120: revisar loadBoard", "Ya quedó: actualiza la página.")
    log = admin("/api/actions", jwt_token=token()).json()["actions"]
    assert [a["after"]["status"] for a in log] == ["closed", "open", "closed", "reviewed"]
    assert all(a["action"] == "feedback" and a["after"]["feedback_id"] == fid for a in log)


def test_closing_without_a_note_says_thanks(admin, api):
    api.login("sin-nota@test.com")
    fid = report(api)
    update(admin, fid, {"status": "closed"})
    assert closed_notices(api)[0]["detail"] == "Gracias por avisarnos."


def test_the_notice_is_only_for_who_reported_it(admin, api):
    api.login("dueno-reporte@test.com")
    fid = report(api)
    update(admin, fid, {"status": "closed", "user_note": "Listo"})
    api.login("otra-persona@test.com")
    assert closed_notices(api) == []


def test_empty_note_clears_it_and_bad_input_is_refused(admin, api):
    api.login("notas@test.com")
    fid = report(api)
    update(admin, fid, {"admin_note": "algo"})
    assert update(admin, fid, {"admin_note": "   "}).json()["admin_note"] is None
    for bad in ({"status": "borrado"}, {"admin_note": "x" * 1001}, {"user_note": "x" * 501}):
        assert update(admin, fid, bad).status_code == 422, bad
    assert update(admin, fid, {"admin_note": "x" * 1000}).status_code == 200
    assert update(admin, fid, {"user_note": "x" * 500}).status_code == 200
    assert update(admin, 999999, {"status": "closed"}).status_code == 404
    # Nada que cambie: nada en la bitácora
    before = len(admin("/api/actions", jwt_token=token()).json()["actions"])
    update(admin, fid, {"user_note": "x" * 500})
    assert len(admin("/api/actions", jwt_token=token()).json()["actions"]) == before
