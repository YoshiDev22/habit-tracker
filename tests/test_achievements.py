"""
Logros (módulo "achievements"): fechas parciales, hitos automáticos, el botón SOS
y los permisos de las evidencias. Los archivos van a la carpeta temporal de las
pruebas (UPLOADS_DIR en conftest.py).
"""
import io
import json
import os
import random
import stat
from datetime import date, timedelta
from pathlib import Path

import pytest
from PIL import Image

from backend import achievement_files, achievements
from conftest import H, client_today, log_time

TODAY = date.today()
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def png(w=60, h=40) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (30, 120, 200)).save(out, "PNG")
    return out.getvalue()


def on(api):
    api.call("PUT", "/api/auth/me/modules/achievements", {"enabled": True}, expect=200)
    return api


def new(api, title="Diploma", date_="2020-05-17", **fields):
    _, a = api.call("POST", "/api/achievements", {"title": title, "date": date_, **fields}, expect=201)
    return a


def upload(api, achievement_id, data, name="evidencia.png", content_type="image/png"):
    headers = {"Authorization": f"Bearer {api.token}"} if api.token else {}
    r = api.client.post(f"/api/achievements/{achievement_id}/files", headers=headers,
                        files={"file": (name, data, content_type)})
    return r.status_code, r.json()


def fetch(api, path):
    headers = {"Authorization": f"Bearer {api.token}"} if api.token else {}
    return api.client.get(path, headers=headers)


def listing(api):
    return api.call("GET", "/api/achievements", expect=200)[1]


# ==================== Módulo ====================

def test_off_by_default_and_blocked_in_the_server(api):
    api.login("yoshi@test.com")
    _, me = api.call("GET", "/api/auth/me", expect=200)
    assert me["modules"]["achievements"] == {"enabled": False, "allowed": True}
    for method, path in [("GET", "/api/achievements"), ("POST", "/api/achievements"), ("GET", "/api/achievements/sos"),
                         ("GET", "/api/achievements/files/1"), ("GET", "/api/achievements/sos/notes")]:
        assert api.call(method, path, {"title": "x", "date": "2020-01"})[0] == 403, path
    on(api)
    out = listing(api)
    assert [c["name"] for c in out["categories"]] == achievements.DEFAULT_CATEGORIES
    assert out["usage"] == {"bytes": 0, "quota": achievement_files.QUOTA_BYTES,
                            "file_max": achievement_files.MAX_FILE_BYTES}
    assert len(api.call("GET", "/api/achievements/sos/actions", expect=200)[1]) == len(achievements.DEFAULT_SOS_ACTIONS)


# ==================== Fechas parciales ====================

def test_month_only_dates(api):
    on(api.login("yoshi@test.com"))
    month = new(api, "Concurso de 2019", "2019-06")
    assert (month["date"], month["date_precision"], month["achieved_on"]) == ("2019-06", "month", "2019-06-01")
    exact = new(api, "Constancia", "2019-06-20")
    assert (exact["date"], exact["date_precision"]) == ("2019-06-20", "day")
    older = new(api, "Diploma", "2018-12-31")
    # Ordenados por fecha, el más reciente arriba: el mes cuenta desde su día 1
    assert [a["id"] for a in listing(api)["achievements"]] == [exact["id"], month["id"], older["id"]]

    _, patched = api.call("PATCH", f"/api/achievements/{month['id']}", {"date": "2019-06-02"}, expect=200)
    assert (patched["date"], patched["date_precision"]) == ("2019-06-02", "day")
    _, patched = api.call("PATCH", f"/api/achievements/{month['id']}", {"date": "2017-03"}, expect=200)
    assert (patched["date"], patched["date_precision"], patched["achieved_on"]) == ("2017-03", "month", "2017-03-01")


@pytest.mark.parametrize("bad", ["2019-13", "2019-02-30", "19-06", "2019/06", "2019", "2019-6", "1899-12", "",
                                 (TODAY + timedelta(days=3)).isoformat()])
def test_bad_dates(api, bad):
    on(api.login("yoshi@test.com"))
    assert api.call("POST", "/api/achievements", {"title": "x", "date": bad})[0] == 422
    a = new(api)
    assert api.call("PATCH", f"/api/achievements/{a['id']}", {"date": bad})[0] == 422


def test_fields_kinds_and_texts(api):
    on(api.login("yoshi@test.com"))
    cats = listing(api)["categories"]
    _, col = api.call("POST", "/api/achievements/collections", {"name": "Impartí clases"}, expect=201)
    a = new(api, "Superé el examen", "2021-02", kind="anecdote", category_id=cats[-1]["id"],
            collection_id=col["id"], situation="  Estaba nervioso  ", what_i_did="Estudié", what_it_shows="",
            is_featured=True)
    assert (a["kind"], a["origin"], a["is_featured"]) == ("anecdote", "manual", True)
    assert (a["situation"], a["what_it_shows"]) == ("Estaba nervioso", None)
    assert api.call("POST", "/api/achievements", {"title": "x", "date": "2020-01", "kind": "medalla"})[0] == 422
    # El origen no lo elige el cliente
    _, b = api.call("POST", "/api/achievements", {"title": "x", "date": "2020-01", "origin": "auto"}, expect=201)
    assert b["origin"] == "manual"
    # Quitar la colección y la categoría con null
    _, a = api.call("PATCH", f"/api/achievements/{a['id']}", {"collection_id": None, "category_id": None}, expect=200)
    assert a["collection_id"] is None and a["category_id"] is None


def test_categories_and_collections(api):
    on(api.login("yoshi@test.com"))
    cats = listing(api)["categories"]
    a = new(api, category_id=cats[0]["id"])
    assert api.call("POST", "/api/achievements/categories", {"name": "Académico"})[0] == 409
    _, extra = api.call("POST", "/api/achievements/categories", {"name": "Deportes"}, expect=201)
    api.call("PATCH", f"/api/achievements/categories/{extra['id']}", {"name": "Deporte"}, expect=200)
    # Borrar una categoría deja sus logros sin categoría
    api.call("DELETE", f"/api/achievements/categories/{cats[0]['id']}", expect=204)
    assert api.call("GET", f"/api/achievements/{a['id']}", expect=200)[1]["category_id"] is None
    for cat in listing(api)["categories"][:-1]:
        api.call("DELETE", f"/api/achievements/categories/{cat['id']}", expect=204)
    last = listing(api)["categories"]
    assert len(last) == 1
    assert api.call("DELETE", f"/api/achievements/categories/{last[0]['id']}")[0] == 409
    # La lista no vuelve a sembrarse
    assert len(listing(api)["categories"]) == 1

    _, col = api.call("POST", "/api/achievements/collections", {"name": "Clases"}, expect=201)
    b = new(api, collection_id=col["id"])
    assert api.call("POST", "/api/achievements/collections", {"name": "Clases"})[0] == 409
    api.call("DELETE", f"/api/achievements/collections/{col['id']}", expect=204)
    assert api.call("GET", f"/api/achievements/{b['id']}", expect=200)[1]["collection_id"] is None


# ==================== Hitos automáticos ====================

def test_project_hour_milestones(seeded):
    api = on(seeded["api"])
    p, task = seeded["project"], seeded["tasks"]["Corrección de Pomodoros"]
    # El seeded ya trae 417 min hoy. Antes, 4 h hace 5 días: cruza las 10 h hoy
    log_time(api, p["id"], task["id"], 4 * H, day=TODAY - timedelta(days=5))
    auto = [a for a in listing(api)["achievements"] if a["origin"] == "auto"]
    assert [(a["title"], a["date"], a["kind"]) for a in auto] == [("10 h de enfoque en Habit Tracker",
                                                                     TODAY.isoformat(), "milestone")]
    # Correr la sincronización otra vez no duplica
    assert len([a for a in listing(api)["achievements"] if a["origin"] == "auto"]) == 1
    # Renombrar el proyecto no cambia un hito ya escrito; 15 h más cruzan las 25
    api.call("PATCH", f"/api/projects/{p['id']}", {"name": "HT"}, expect=200)
    log_time(api, p["id"], task["id"], 15 * H)
    titles = sorted(a["title"] for a in listing(api)["achievements"] if a["origin"] == "auto")
    assert titles == ["10 h de enfoque en Habit Tracker", "25 h de enfoque en HT"]


def test_unassigned_and_breaks_never_make_milestones(seeded):
    api = on(seeded["api"])
    _, projects = api.call("GET", "/api/projects", expect=200)
    inbox = next(p for p in projects["projects"] if p["name"] == "Sin asignar")
    log_time(api, inbox["id"], None, 11 * H)
    log_time(api, seeded["project"]["id"], None, 11 * H, mode="short_break")
    assert [a for a in listing(api)["achievements"] if a["origin"] == "auto"] == []


def test_habit_day_milestones(api):
    on(api.login("yoshi@test.com"))
    api.call("POST", "/api/habits/definitions", {"key": "leer", "label": "Leer"}, expect=201)
    days = [TODAY - timedelta(days=20 - i) for i in range(11)]
    for day in days:
        api.call("PATCH", f"/api/habits/day/{day}", {"habit_key": "leer", "done": True}, expect=200)
    auto = [a for a in listing(api)["achievements"] if a["origin"] == "auto"]
    assert [(a["title"], a["date"]) for a in auto] == [("10 días cumplidos de Leer", days[9].isoformat())]


def test_habit_milestones_wait_for_the_habits_module(api):
    on(api.login("yoshi@test.com"))
    api.call("POST", "/api/habits/definitions", {"key": "leer", "label": "Leer"}, expect=201)
    for i in range(10):
        api.call("PATCH", f"/api/habits/day/{TODAY - timedelta(days=i + 1)}", {"habit_key": "leer", "done": True},
                 expect=200)
    api.call("PUT", "/api/auth/me/modules/habits", {"enabled": False}, expect=200)
    assert [a for a in listing(api)["achievements"] if a["origin"] == "auto"] == []
    api.call("PUT", "/api/auth/me/modules/habits", {"enabled": True}, expect=200)
    assert len([a for a in listing(api)["achievements"] if a["origin"] == "auto"]) == 1


def test_hide_and_delete_a_milestone(seeded):
    api = on(seeded["api"])
    log_time(api, seeded["project"]["id"], None, 4 * H)
    hito = next(a for a in listing(api)["achievements"] if a["origin"] == "auto")
    _, hidden = api.call("PATCH", f"/api/achievements/{hito['id']}", {"is_hidden": True}, expect=200)
    assert hidden["is_hidden"] is True
    assert next(a for a in listing(api)["achievements"] if a["id"] == hito["id"])["is_hidden"] is True
    api.call("DELETE", f"/api/achievements/{hito['id']}", expect=204)
    # Borrado: no sale, no se puede leer y no vuelve a generarse
    assert all(a["id"] != hito["id"] for a in listing(api)["achievements"])
    assert api.call("GET", f"/api/achievements/{hito['id']}")[0] == 404
    assert [a for a in listing(api)["achievements"] if a["origin"] == "auto"] == []


def test_crossings():
    d = [date(2026, 1, i) for i in range(1, 6)]
    assert achievements._crossings([(d[0], 6), (d[1], 3), (d[2], 1), (d[3], 20)], [10, 25, 50]) == \
        {10: d[2], 25: d[3]}
    assert achievements._crossings([(d[0], 60)], [10, 25, 50]) == {10: d[0], 25: d[0], 50: d[0]}
    assert achievements._crossings([], [10]) == {}


# ==================== Botón SOS ====================

def test_sos_never_repeats_within_one_opening(api, monkeypatch):
    on(api.login("yoshi@test.com"))
    monkeypatch.setattr(achievements, "rng", random.Random(7))
    ids = {new(api, f"Logro {i}", f"2020-0{i}")["id"] for i in range(1, 8)}
    hidden = new(api, "Oculto", "2020-09")
    api.call("PATCH", f"/api/achievements/{hidden['id']}", {"is_hidden": True}, expect=200)
    seen = []
    for _ in range(3):   # 3 + 3 + 1
        _, out = api.call("GET", f"/api/achievements/sos?exclude={','.join(map(str, seen))}", expect=200)
        shown = [a["id"] for a in out["achievements"]]
        assert len(shown) == len(set(shown)) and not set(shown) & set(seen)
        assert out["restarted"] is False
        seen += shown
    assert sorted(seen) == sorted(ids)
    # Ya se vieron todos: vuelve a empezar, y lo dice
    _, out = api.call("GET", f"/api/achievements/sos?exclude={','.join(map(str, seen))}", expect=200)
    assert out["restarted"] is True and len(out["achievements"]) == 3
    assert hidden["id"] not in [a["id"] for a in out["achievements"]]
    assert api.call("GET", "/api/achievements/sos?exclude=1,a")[0] == 422


def test_sos_prefers_anecdotes_and_featured():
    rng = random.Random(1)
    real = achievements.rng
    achievements.rng = rng
    try:
        class A:
            def __init__(self, id, kind="diploma", is_featured=False):
                self.id, self.kind, self.is_featured = id, kind, is_featured
        pool = [A(1, "anecdote"), A(2, is_featured=True), A(3), A(4)]
        first = {}
        for _ in range(4000):
            picked, _ = achievements.pick_achievements(pool, [], count=1)
            first[picked[0].id] = first.get(picked[0].id, 0) + 1
    finally:
        achievements.rng = real
    # Peso 3 frente a 1: 3/8 de las veces cada uno de los pesados, 1/8 los demás
    assert first[1] > 2 * first[3] and first[2] > 2 * first[4]
    assert 1200 < first[1] < 1800


def test_sos_fact_is_cumulative_and_never_empty(seeded, monkeypatch):
    api = on(seeded["api"])
    _, out = api.call("GET", "/api/achievements/sos", expect=200)
    assert out["achievements"] == []
    assert out["action"]["text"] in achievements.DEFAULT_SOS_ACTIONS
    facts = set()
    for seed in range(30):
        monkeypatch.setattr(achievements, "rng", random.Random(seed))
        facts.add(api.call("GET", "/api/achievements/sos", expect=200)[1]["fact"])
    # 417 min hoy en Habit Tracker y 4 tareas terminadas, siempre en total
    assert facts == {"Llevas 7 h de enfoque registradas en Habit Tracker.",
                     "Has terminado 4 tareas desde que usas la app."}


def test_sos_without_data(api):
    on(api.login("yoshi@test.com"))
    _, out = api.call("GET", "/api/achievements/sos", expect=200)
    assert out["fact"] is None and out["achievements"] == [] and out["restarted"] is False


def test_sos_actions_and_notes(api):
    on(api.login("yoshi@test.com"))
    actions = api.call("GET", "/api/achievements/sos/actions", expect=200)[1]
    _, mine = api.call("POST", "/api/achievements/sos/actions", {"text": "Escribir un párrafo"}, expect=201)
    api.call("PATCH", f"/api/achievements/sos/actions/{mine['id']}", {"text": "Escribir dos párrafos"}, expect=200)
    for action in actions:
        api.call("DELETE", f"/api/achievements/sos/actions/{action['id']}", expect=204)
    assert api.call("DELETE", f"/api/achievements/sos/actions/{mine['id']}")[0] == 409
    assert api.call("GET", "/api/achievements/sos", expect=200)[1]["action"]["text"] == "Escribir dos párrafos"

    _, note = api.call("POST", "/api/achievements/sos/notes", {"note_date": str(client_today()), "body": " Cansado "},
                       expect=201)
    assert note["body"] == "Cansado"
    assert [n["id"] for n in api.call("GET", "/api/achievements/sos/notes", expect=200)[1]] == [note["id"]]
    assert api.call("POST", "/api/achievements/sos/notes", {"note_date": str(client_today()), "body": "   "})[0] == 422
    api.call("DELETE", f"/api/achievements/sos/notes/{note['id']}", expect=204)
    assert api.call("GET", "/api/achievements/sos/notes", expect=200)[1] == []


def test_sos_notes_never_reach_reports_exports_or_metrics(api):
    on(api.login("yoshi@test.com"))
    api.call("POST", "/api/habits/definitions", {"key": "leer", "label": "Leer"}, expect=201)
    api.call("PATCH", f"/api/habits/day/{TODAY}", {"habit_key": "leer", "done": True}, expect=200)
    api.call("POST", "/api/achievements/sos/notes", {"note_date": str(TODAY), "body": "NOTA-SOS-PRIVADA"}, expect=201)
    new(api, "LOGRO-PRIVADO", situation="SITUACION-PRIVADA")
    monday = TODAY - timedelta(days=TODAY.weekday())
    outputs = [
        api.call("POST", "/api/reports", {"kind": kind, "period_start": monday.isoformat(), "today": TODAY.isoformat()},
                 expect=200)[1]
        for kind in ("week", "habits-week")
    ]
    outputs.append(api.call("GET", f"/api/habits/export?date_from={monday}&date_to={TODAY}&today={TODAY}",
                            expect=200)[1])
    outputs.append(api.call("GET", f"/api/metrics?date_from={monday}&date_to={TODAY}", expect=200)[1])
    for out in outputs:
        text = json.dumps(out, ensure_ascii=False)
        assert "PRIVAD" not in text


# ==================== Evidencias ====================

def test_upload_image_and_pdf(api):
    on(api.login("yoshi@test.com"))
    a = new(api)
    status, img = upload(api, a["id"], png(1200, 800), name="..\\..\\diploma.png")
    assert status == 201, img
    assert (img["mime"], img["has_thumb"], img["original_name"]) == ("image/png", True, "diploma.png")
    status, pdf = upload(api, a["id"], PDF, name="constancia.pdf", content_type="application/pdf")
    assert status == 201 and (pdf["mime"], pdf["has_thumb"]) == ("application/pdf", False)

    r = fetch(api, f"/api/achievements/files/{img['id']}")
    assert r.status_code == 200 and r.content == png(1200, 800)
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff" and "no-store" in r.headers["cache-control"]
    assert "sandbox" in r.headers["content-security-policy"]
    thumb = fetch(api, f"/api/achievements/files/{img['id']}/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"
    assert max(Image.open(io.BytesIO(thumb.content)).size) == achievement_files.THUMB_SIZE
    assert fetch(api, f"/api/achievements/files/{pdf['id']}/thumb").status_code == 404
    assert fetch(api, f"/api/achievements/files/{pdf['id']}").content == PDF

    files = listing(api)["achievements"][0]["files"]
    assert [f["id"] for f in files] == [img["id"], pdf["id"]]
    assert listing(api)["usage"]["bytes"] == len(png(1200, 800)) + len(PDF)


def test_files_live_outside_the_repo_and_are_private(api):
    on(api.login("yoshi@test.com"))
    a = new(api)
    upload(api, a["id"], png())
    root = Path(os.environ["UPLOADS_DIR"]).resolve()
    repo = Path(__file__).resolve().parents[1]
    assert repo not in root.parents
    folder = achievement_files.user_dir(api.call("GET", "/api/auth/me", expect=200)[1]["id"])
    stored = sorted(p.name for p in folder.iterdir())
    assert len(stored) == 2 and all(len(n.split(".")[0]) == 32 for n in stored)   # nombres aleatorios
    if os.name == "posix":
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in folder.iterdir())


@pytest.mark.parametrize("data,name,content_type", [
    (b"hola, no soy una imagen", "foto.png", "image/png"),                 # el nombre y el tipo mienten
    (b"\x89PNG\r\n\x1a\n" + b"basura" * 50, "foto.png", "image/png"),      # la firma de PNG, sin imagen
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "x.svg", "image/svg+xml"),
    (b"GIF89a" + b"\x00" * 40, "x.gif", "image/gif"),
    (b"", "vacio.pdf", "application/pdf"),
])
def test_only_real_pdf_jpg_png_webp(api, data, name, content_type):
    on(api.login("yoshi@test.com"))
    a = new(api)
    status, out = upload(api, a["id"], data, name=name, content_type=content_type)
    assert status == 422, out
    assert listing(api)["achievements"][0]["files"] == []


def test_a_jpeg_named_png_is_kept_as_jpeg(api):
    on(api.login("yoshi@test.com"))
    a = new(api)
    out = io.BytesIO()
    Image.new("RGB", (20, 20)).save(out, "JPEG")
    status, f = upload(api, a["id"], out.getvalue(), name="foto.png", content_type="image/png")
    assert status == 201 and f["mime"] == "image/jpeg"


def test_size_limits(api, monkeypatch):
    on(api.login("yoshi@test.com"))
    a = new(api)
    monkeypatch.setattr(achievement_files, "MAX_FILE_BYTES", 400)
    assert upload(api, a["id"], PDF + b"%" * 500, name="grande.pdf", content_type="application/pdf")[0] == 413
    # Sin Content-Length no se lee el formulario
    r = api.client.post(f"/api/achievements/{a['id']}/files", headers={"Authorization": f"Bearer {api.token}",
                                                                       "Content-Type": "multipart/form-data; boundary=x"},
                        content=iter([b"--x--\r\n"]))
    assert r.status_code == 411
    monkeypatch.setattr(achievement_files, "MAX_FILE_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(achievement_files, "QUOTA_BYTES", len(PDF) * 2 + 10)
    assert upload(api, a["id"], PDF, name="1.pdf", content_type="application/pdf")[0] == 201
    assert upload(api, a["id"], PDF, name="2.pdf", content_type="application/pdf")[0] == 201
    status, out = upload(api, a["id"], PDF, name="3.pdf", content_type="application/pdf")
    assert status == 413 and "espacio" in out["detail"]
    monkeypatch.setattr(achievement_files, "QUOTA_BYTES", 10 ** 9)
    monkeypatch.setattr(achievement_files, "MAX_FILES_PER_ACHIEVEMENT", 2)
    assert upload(api, a["id"], PDF, name="3.pdf", content_type="application/pdf")[0] == 409


def test_decompression_bomb_is_rejected(api, monkeypatch):
    on(api.login("yoshi@test.com"))
    a = new(api)
    monkeypatch.setattr(achievement_files.Image, "MAX_IMAGE_PIXELS", 1000)
    status, out = upload(api, a["id"], png(100, 100))
    assert status == 422 and "píxeles" in out["detail"]


def test_file_permissions(seeded):
    api, other = on(seeded["api"]), on(seeded["other"])
    a = new(api)
    _, f = upload(api, a["id"], png())
    for path in (f"/api/achievements/files/{f['id']}", f"/api/achievements/files/{f['id']}/thumb"):
        assert fetch(api, path).status_code == 200
        assert fetch(other, path).status_code == 404            # otra cuenta: ni sabe que existe
        assert api.client.get(path).status_code == 401           # sin sesión
        assert api.client.get(path, headers={"Authorization": "Bearer basura"}).status_code == 401
    assert other.call("DELETE", f"/api/achievements/files/{f['id']}")[0] == 404
    assert upload(other, a["id"], png())[0] == 404              # subir a un logro ajeno
    # Con el módulo apagado, ni el dueño
    api.call("PUT", "/api/auth/me/modules/achievements", {"enabled": False}, expect=200)
    assert fetch(api, f"/api/achievements/files/{f['id']}").status_code == 403
    on(api)
    api.call("DELETE", f"/api/achievements/files/{f['id']}", expect=204)
    assert fetch(api, f"/api/achievements/files/{f['id']}").status_code == 404


def test_deleting_removes_files_from_disk(api):
    on(api.login("yoshi@test.com"))
    me = api.call("GET", "/api/auth/me", expect=200)[1]
    folder = achievement_files.user_dir(me["id"])
    a = new(api)
    upload(api, a["id"], png())
    upload(api, a["id"], PDF, name="c.pdf", content_type="application/pdf")
    assert len(list(folder.iterdir())) == 3   # imagen, su miniatura y el PDF
    _, f = upload(api, new(api, "Otro")["id"], png())
    api.call("DELETE", f"/api/achievements/{a['id']}", expect=204)
    assert len(list(folder.iterdir())) == 2
    api.call("DELETE", f"/api/achievements/files/{f['id']}", expect=204)
    assert list(folder.iterdir()) == []


def test_deleting_the_account_removes_its_folder(api):
    on(api.login("yoshi@test.com"))
    me = api.call("GET", "/api/auth/me", expect=200)[1]
    upload(api, new(api)["id"], png())
    api.call("POST", "/api/achievements/sos/notes", {"note_date": str(TODAY), "body": "x"}, expect=201)
    assert achievement_files.user_dir(me["id"]).exists()
    api.call("POST", "/api/auth/me/delete", {"mode": "now", "password": "secret123", "confirm": "BORRAR"}, expect=204)
    assert not achievement_files.user_dir(me["id"]).exists()

