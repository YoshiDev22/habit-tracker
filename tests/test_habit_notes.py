"""Notas por día en los hábitos (1.25): se guardan aparte, no cambian la racha."""
from datetime import date, timedelta

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def setup(api, email="notas@test.com"):
    api.login(email)
    api.call("POST", "/api/habits/definitions", {"key": "ejercicio", "label": "Ejercicio"}, expect=201)
    api.call("PATCH", f"/api/habits/day/{YESTERDAY}", {"habit_key": "ejercicio", "done": True}, expect=200)


def notes(api, start=YESTERDAY, end=TODAY):
    return api.call("GET", f"/api/habits/notes?date_from={start}&date_to={end}", expect=200)[1]["notes"]


def test_write_change_and_clear_a_note(api):
    setup(api)
    _, note = api.call("PUT", f"/api/habits/notes/{YESTERDAY}/ejercicio", {"text": "  cuerda   20 min  "}, expect=200)
    assert note == {"habit_key": "ejercicio", "date": YESTERDAY.isoformat(), "text": "cuerda 20 min"}
    api.call("PUT", f"/api/habits/notes/{YESTERDAY}/ejercicio", {"text": "bici a la escuela"}, expect=200)
    assert [n["text"] for n in notes(api)] == ["bici a la escuela"]
    # Una nota no marca el hábito ni cambia la racha
    _, streak = api.call("GET", f"/api/habits/streak?today={TODAY}", expect=200)
    api.call("PUT", f"/api/habits/notes/{TODAY}/ejercicio", {"text": "solo una nota"}, expect=200)
    _, after = api.call("GET", f"/api/habits/streak?today={TODAY}", expect=200)
    assert after["streak"] == streak["streak"]
    # Vacía: se borra
    status, body = api.call("PUT", f"/api/habits/notes/{TODAY}/ejercicio", {"text": "   "})
    assert status == 200 and body is None
    assert [n["date"] for n in notes(api)] == [YESTERDAY.isoformat()]


def test_note_rules(api):
    setup(api)
    assert api.call("PUT", f"/api/habits/notes/{TODAY}/noexiste", {"text": "x"})[0] == 404
    assert api.call("PUT", f"/api/habits/notes/{TODAY}/ejercicio", {"text": "x" * 201})[0] == 422
    assert api.call("PUT", f"/api/habits/notes/{TODAY}/ejercicio", {"text": "x" * 200}, expect=200)[0] == 200
    assert api.call("GET", f"/api/habits/notes?date_from={TODAY}&date_to={YESTERDAY}")[0] == 422
    far = TODAY - timedelta(days=400)
    assert api.call("GET", f"/api/habits/notes?date_from={far}&date_to={TODAY}")[0] == 422


def test_notes_are_private(api):
    setup(api)
    api.call("PUT", f"/api/habits/notes/{YESTERDAY}/ejercicio", {"text": "mía"}, expect=200)
    # Otra cuenta con un hábito de la misma clave no ve ni toca la nota
    setup(api, "otra-notas@test.com")
    assert notes(api) == []
    api.call("PUT", f"/api/habits/notes/{YESTERDAY}/ejercicio", {"text": "suya"}, expect=200)
    api.login("notas@test.com")
    assert [n["text"] for n in notes(api)] == ["mía"]


def test_notes_in_the_csv_and_the_report(api):
    setup(api)
    api.call("PUT", f"/api/habits/notes/{YESTERDAY}/ejercicio", {"text": "cuerda 20 min"}, expect=200)
    _, export = api.call("GET", f"/api/habits/export?date_from={YESTERDAY}&date_to={TODAY}&today={TODAY}", expect=200)
    row = next(r for r in export["rows"] if r["date"] == YESTERDAY.isoformat())
    assert row["note"] == "cuerda 20 min"
    monday = YESTERDAY - timedelta(days=YESTERDAY.weekday())
    _, rep = api.call("POST", "/api/reports", {"kind": "habits-week", "period_start": monday.isoformat(),
                                               "today": TODAY.isoformat()}, expect=200)
    assert rep["metrics"]["notes"] == [{"date": YESTERDAY.isoformat(), "habit": "Ejercicio", "text": "cuerda 20 min"}]
    assert any("Anotaste 1 nota" in p for p in rep["text"]["patterns"])
