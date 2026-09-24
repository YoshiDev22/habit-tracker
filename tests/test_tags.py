"""Etiquetas: varias por tarea; sus totales cuentan doble, el combinado no."""
from datetime import date, timedelta

from conftest import H, log_time


def test_create_validate_list(seeded):
    api = seeded["api"]
    _, doc = api.call("POST", "/api/tags", {"name": "documentación", "color": "#123456"}, expect=201)
    _, adm = api.call("POST", "/api/tags", {"name": "  administrativa "}, expect=201)
    assert adm["name"] == "administrativa"
    assert api.call("POST", "/api/tags", {"name": "documentación"})[0] == 409
    assert api.call("POST", "/api/tags", {"name": "x", "color": "azul"})[0] == 422
    assert api.call("POST", "/api/tags", {"name": "x" * 31})[0] == 422
    _, tg = api.call("GET", "/api/tags", expect=200)
    assert [t["name"] for t in tg["tags"]] == ["administrativa", "documentación"]


def test_tags_on_tasks(seeded):
    api = seeded["api"]
    corr = seeded["tasks"]["Corrección de Pomodoros"]
    conf = seeded["tasks"]["Confirmación de guardado de datos en hábitos"]
    _, doc = api.call("POST", "/api/tags", {"name": "doc"}, expect=201)
    _, adm = api.call("POST", "/api/tags", {"name": "adm"}, expect=201)
    _, r = api.call("PATCH", f"/api/tasks/{corr['id']}", {"tag_ids": [doc["id"], adm["id"], doc["id"]]}, expect=200)
    assert sorted(r["tag_ids"]) == sorted([doc["id"], adm["id"]])
    api.call("PATCH", f"/api/tasks/{conf['id']}", {"tag_ids": [doc["id"]]}, expect=200)
    _, r = api.call("PATCH", f"/api/tasks/{conf['id']}", {"title": conf["title"]}, expect=200)
    assert r["tag_ids"] == [doc["id"]], "omitting tag_ids keeps them"
    _, t = api.call("POST", "/api/tasks", {"title": "nueva", "tag_ids": [adm["id"]]}, expect=201)
    assert t["tag_ids"] == [adm["id"]]
    assert api.call("PATCH", f"/api/tasks/{t['id']}", {"tag_ids": []}, expect=200)[1]["tag_ids"] == []

    _, f = api.call("GET", f"/api/tasks?tag_id={doc['id']}", expect=200)
    assert {x["id"] for x in f["tasks"]} == {corr["id"], conf["id"]}

    # Borrar una etiqueta la quita de sus tareas; borrar una tarea quita sus enlaces
    api.call("DELETE", f"/api/tags/{adm['id']}", expect=204)
    _, tl = api.call("GET", "/api/tasks", expect=200)
    assert next(x for x in tl["tasks"] if x["id"] == corr["id"])["tag_ids"] == [doc["id"]]
    api.call("DELETE", f"/api/tasks/{conf['id']}", expect=204)
    _, sm = api.call("GET", "/api/tags/summary", expect=200)
    assert sm["summaries"][0]["task_count"] == 1


def test_tag_summary_counts_once_when_combined(seeded):
    api = seeded["api"]
    corr = seeded["tasks"]["Corrección de Pomodoros"]           # 4 h
    conf = seeded["tasks"]["Confirmación de guardado de datos en hábitos"]  # 35 min
    _, doc = api.call("POST", "/api/tags", {"name": "doc"}, expect=201)
    _, adm = api.call("POST", "/api/tags", {"name": "adm"}, expect=201)
    api.call("PATCH", f"/api/tasks/{corr['id']}", {"tag_ids": [doc["id"], adm["id"]]}, expect=200)
    api.call("PATCH", f"/api/tasks/{conf['id']}", {"tag_ids": [doc["id"]]}, expect=200)
    # Tiempo sin tarea: cuenta como "sin etiqueta"
    log_time(api, seeded["project"]["id"], None, 20 * 60)
    total = 417 * 60 + 20 * 60

    _, sm = api.call("GET", f"/api/tags/summary?tag_ids={doc['id']}&tag_ids={adm['id']}", expect=200)
    per = {x["name"]: x["total_seconds"] for x in sm["summaries"]}
    assert per == {"doc": 4 * H + 35 * 60, "adm": 4 * H}
    assert sm["combined_seconds"] == 4 * H + 35 * 60      # no 8 h 35
    assert sm["combined_seconds"] + sm["untagged_seconds"] == total
    _, only_adm = api.call("GET", f"/api/tags/summary?tag_ids={adm['id']}", expect=200)
    assert only_adm["combined_seconds"] == 4 * H
    later = (date.today() + timedelta(days=2)).isoformat()
    _, sm = api.call("GET", f"/api/tags/summary?date_from={later}", expect=200)
    assert all(x["total_seconds"] == 0 for x in sm["summaries"])
    # El total por proyecto sigue exacto
    _, ps = api.call("GET", "/api/projects/summary", expect=200)
    assert next(x for x in ps["summaries"] if x["name"] == "Habit Tracker")["total_seconds"] == total
