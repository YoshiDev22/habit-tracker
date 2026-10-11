"""No se pueden registrar ni corregir horas que todavía no pasan (bug de la 1.27): el
servidor solo comparaba el día, así que hoy más tarde que ahora se aceptaba."""
from datetime import date, timedelta

from conftest import log_time, utc_now

FUTURE = "No puedes poner horas futuras"


def entry(project_id, start, seconds, source="manual"):
    return {"project_id": project_id, "task_id": None, "session_date": date.today().isoformat(),
            "started_at": start.isoformat(), "ended_at": (start + timedelta(seconds=seconds)).isoformat(),
            "duration_seconds": seconds, "planned_seconds": seconds, "mode": "focus",
            "was_completed": True, "source": source, "note": None}


def test_logging_by_hand_cannot_end_later_than_now(seeded):
    api, pid = seeded["api"], seeded["project"]["id"]
    later = utc_now() + timedelta(hours=2)
    status, body = api.call("POST", "/api/pomodoro", entry(pid, later, 1800))
    assert status == 400 and FUTURE in body["detail"]
    # Empezó hace media hora y terminaría en otra media: tampoco
    status, body = api.call("POST", "/api/pomodoro", entry(pid, utc_now() - timedelta(minutes=30), 3600))
    assert status == 400 and FUTURE in body["detail"]
    # Termina justo ahora (o con un reloj medio minuto adelantado): sí
    api.call("POST", "/api/pomodoro", entry(pid, utc_now() - timedelta(minutes=30), 1800), expect=201)
    api.call("POST", "/api/pomodoro", entry(pid, utc_now() - timedelta(minutes=29, seconds=30), 1800), expect=201)
    # Con la zona horaria escrita (Z): igual
    start = (utc_now() + timedelta(hours=1)).isoformat() + "+00:00"
    body = {**entry(pid, utc_now(), 600), "started_at": start,
            "ended_at": (utc_now() + timedelta(hours=1, minutes=10)).isoformat() + "+00:00"}
    assert api.call("POST", "/api/pomodoro", body)[0] == 400


def test_correcting_a_record_cannot_move_it_to_later_than_now(seeded):
    api, pid = seeded["api"], seeded["project"]["id"]
    s = log_time(api, pid, None, 1800)
    url = f"/api/pomodoro/{s['id']}"
    later = utc_now() + timedelta(hours=1)
    status, body = api.call("PATCH", url, {"started_at": later.isoformat(),
                                          "ended_at": (later + timedelta(minutes=30)).isoformat()})
    assert status == 400 and FUTURE in body["detail"]
    status, body = api.call("PATCH", url, {"duration_seconds": 1800 + 7200,
                                          "ended_at": (utc_now() + timedelta(hours=2)).isoformat()})
    assert status == 400 and FUTURE in body["detail"]
    # Lo que no toca las horas se guarda como siempre
    assert api.call("PATCH", url, {"note": "revisado"}, expect=200)[1]["note"] == "revisado"


def test_the_timer_is_not_refused_for_a_fast_clock(seeded):
    """El timer manda su propia hora: si el reloj del dispositivo va adelantado, se
    guarda igual (rechazarla haría que la cola de reenvío no la guardara nunca)."""
    api, pid = seeded["api"], seeded["project"]["id"]
    fast = utc_now() + timedelta(minutes=5)
    for source in ("timer", "stopwatch"):
        api.call("POST", "/api/pomodoro", entry(pid, fast - timedelta(minutes=25), 1500, source=source), expect=201)
