"""IA para el texto de los reportes (épica 30, Fase 5), con un proveedor falso."""
import json
from datetime import date

import pytest
from sqlmodel import Session, select

from backend import report_ai
from backend.ai import AiError, AiReply
from backend.database import engine
from backend.models import AiCall, User, UserModule
from test_metrics import MON, TUE, post

TODAY = date.today()
GOOD = {
    "summary": "Registraste 3 h 30 min en 2 días.",
    "observations": ["Tesis se llevó todo el tiempo.", "El lunes trabajaste 2 h."],
    "recommendations": [],
    "closing": "Buen periodo.",
}


def grant(email, enabled=True):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).one()
        session.add(UserModule(user_id=user.id, module="ai", allowed=True, enabled=enabled))
        session.commit()


@pytest.fixture
def provider(monkeypatch):
    """Configura un proveedor y guarda lo que se le manda; responde `reply`."""
    monkeypatch.setenv("AI_PROVIDER", "cloudflare")
    monkeypatch.setenv("AI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AI_MODEL", "modelo-de-prueba")
    monkeypatch.setenv("AI_DAILY_LIMIT", "3")
    state = {"reply": json.dumps(GOOD, ensure_ascii=False), "sent": []}

    def fake(config, system, user, max_tokens=4000):
        state["sent"].append(json.loads(user))
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return AiReply(content=state["reply"], input_tokens=900, output_tokens=300)

    monkeypatch.setattr(report_ai, "chat_completion", fake)
    return state


def setup(api, email="ia@test.com"):
    api.login(email)
    _, project = api.call("POST", "/api/projects", {"name": "Tesis"}, expect=201)
    _, task = api.call("POST", "/api/tasks", {"project_id": project["id"], "title": "Capítulo 2"}, expect=201)
    post(api, project, task, MON, 9, 120)
    post(api, project, task, TUE, 10, 90)
    return project, task


def generate(api, **extra):
    return api.call("POST", "/api/reports", {"kind": "week", "period_start": MON.isoformat(),
                                             "today": TODAY.isoformat(), **extra}, expect=200)[1]


def test_without_access_the_rules_write(api, provider):
    setup(api)
    rep = generate(api)
    assert rep["text_source"] == "rules" and rep["text_note"] is None and provider["sent"] == []
    assert api.call("POST", f"/api/reports/{rep['id']}/rewrite")[0] == 403
    assert api.call("GET", "/api/reports/ai-preview")[0] == 403


def test_ai_writes_the_text(api, provider):
    setup(api)
    grant("ia@test.com")
    rep = generate(api)
    assert rep["text_source"] == "ai" and rep["text_model"] == "modelo-de-prueba", rep["text_note"]
    assert rep["text"] == GOOD
    sent = provider["sent"][0]
    # Minutos y sin ids ni colores
    assert sent["period"] == "semana" and sent["metrics"]["total_minutes"] == 210
    assert "project_id" not in json.dumps(sent) and "color" not in json.dumps(sent)
    assert sent["metrics"]["by_project"][0]["name"] == "Tesis"
    # use_ai=false: las reglas, sin llamar
    rep = generate(api, use_ai=False)
    assert rep["text_source"] == "rules" and len(provider["sent"]) == 1


def test_invented_numbers_fall_back_to_rules(api, provider, monkeypatch):
    monkeypatch.setenv("AI_DAILY_LIMIT", "10")   # cuatro intentos aquí
    setup(api)
    grant("ia@test.com")
    provider["reply"] = json.dumps({**GOOD, "closing": "Trabajaste 37 h este mes."})
    rep = generate(api)
    assert rep["text_source"] == "rules" and "37" in rep["text_note"]
    assert rep["text"]["summary"].startswith("Registraste 3 h 30 min")
    # Texto con basura alrededor y bloque de código: se acepta si el JSON es bueno
    provider["reply"] = "Claro:\n```json\n" + json.dumps(GOOD) + "\n```"
    assert generate(api)["text_source"] == "ai"
    # Forma incorrecta
    provider["reply"] = json.dumps({"summary": "Hola"})
    assert "observations" in generate(api)["text_note"]
    # El proveedor falla
    provider["reply"] = AiError("No se pudo conectar con el proveedor de IA")
    rep = generate(api)
    assert rep["text_source"] == "rules" and rep["text_note"] == "No se pudo conectar con el proveedor de IA"


def test_daily_limit_and_calls_log(api, provider):
    setup(api)
    grant("ia@test.com")
    for _ in range(3):
        assert generate(api)["text_source"] == "ai"
    rep = generate(api)
    assert rep["text_source"] == "rules" and "límite de 3" in rep["text_note"]
    assert len(provider["sent"]) == 3
    with Session(engine) as session:
        calls = session.exec(select(AiCall)).all()
        assert len(calls) == 3 and all(c.ok and c.input_tokens == 900 for c in calls)


def test_rewrite_and_preview(api, provider):
    setup(api)
    rep = generate(api)                      # sin módulo: reglas
    grant("ia@test.com")
    _, again = api.call("POST", f"/api/reports/{rep['id']}/rewrite", expect=200)
    assert again["id"] == rep["id"] and again["text_source"] == "ai" and again["total_seconds"] == rep["total_seconds"]
    provider["reply"] = AiError("El proveedor de IA rechazó la clave (401)")
    status, body = api.call("POST", f"/api/reports/{rep['id']}/rewrite")
    assert status == 502 and "401" in body["detail"]
    assert api.call("GET", f"/api/reports/{rep['id']}", expect=200)[1]["text_source"] == "ai"

    _, pv = api.call("GET", "/api/reports/ai-preview", expect=200)
    assert pv["configured"] and pv["provider"] == "cloudflare" and pv["model"] == "modelo-de-prueba"
    assert pv["daily_limit"] == 3 and pv["used_today"] == 2 and pv["training_warning"] is False
    assert pv["payload"]["metrics"]["total_minutes"] == 210 and "Responde SOLO" in pv["system"]


def test_module_off_and_unconfigured(api, provider, monkeypatch):
    setup(api)
    grant("ia@test.com", enabled=False)
    rep = generate(api)
    assert rep["text_source"] == "rules" and rep["text_note"] is None
    assert api.call("POST", f"/api/reports/{rep['id']}/rewrite")[0] == 403
    assert api.call("GET", "/api/reports/ai-preview")[0] == 200     # con acceso, aunque esté apagado
    api.call("PUT", "/api/auth/me/modules/ai", {"enabled": True}, expect=200)
    monkeypatch.setenv("AI_BASE_URL", "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1")
    rep = generate(api)
    assert rep["text_note"] == "La IA no está configurada en este servidor"
    assert api.call("POST", f"/api/reports/{rep['id']}/rewrite")[0] == 503
    assert api.call("GET", "/api/reports/ai-preview", expect=200)[1]["configured"] is False


def test_isolation(api, provider):
    setup(api)
    grant("ia@test.com")
    rep = generate(api)
    other = api.as_user("otro-ia@test.com")
    grant("otro-ia@test.com")
    assert other.call("POST", f"/api/reports/{rep['id']}/rewrite")[0] == 404
    # Su vista previa no trae mis cifras
    _, pv = other.call("GET", "/api/reports/ai-preview", expect=200)
    assert pv["payload"]["metrics"]["total_minutes"] == 0


def test_allowed_numbers():
    payload = report_ai.ai_payload("week", {
        "total_seconds": 25020, "by_project": [{"project_id": 1, "name": "Capítulo 7", "color": "#fff",
                                                  "seconds": 25020, "pct": 100}],
        "schedule": {"usual_start": 9.5, "usual_end": 18.25}, "missing_workdays": ["2026-09-29"],
        "previous": {"total_seconds": 7200},
    })
    allowed = report_ai.allowed_numbers(payload)
    for n in (417, 6, 57, 7.0, 100, 9, 30, 18, 15, 29, 2026, 120, 248, 297):
        assert float(n) in allowed or any(abs(n - a) < 0.051 for a in allowed), n
    assert not any(abs(37 - a) < 0.051 for a in allowed)


def test_numbers_with_thousands_and_minutes_everywhere():
    metrics = {"total_seconds": 1580 * 60, "avg_seconds_per_active_day": 790 * 60,
               "seconds_after_16h": 95 * 60, "median_seconds_per_active_day": None,
               "by_project": [], "previous": {"total_seconds": 275 * 60}}
    payload = report_ai.ai_payload("week", metrics)
    m = payload["metrics"]
    # Todo lo que era segundos llega en minutos, también a media palabra
    assert m["total_minutes"] == 1580 and m["avg_minutes_per_active_day"] == 790
    assert m["minutes_after_16h"] == 95 and m["median_minutes_per_active_day"] is None
    assert "seconds" not in json.dumps(payload)

    def text(summary):
        return json.dumps({**GOOD, "summary": summary})
    # "1 580", "1,580" y "1.580" son el total; "26 h 20 min" su conversión
    for written in ("1 580 minutos", "1 580 minutos", "1,580 minutos", "1.580 minutos", "26 h 20 min", "475 %"):
        assert report_ai.validate_text(text(f"Registraste {written}."), payload)
    # Pero un número que no está, aunque lleve separador, no
    with pytest.raises(AiError, match="2580"):
        report_ai.validate_text(text("Registraste 2 580 minutos."), payload)
