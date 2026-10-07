"""Reportes de hábitos y de costos (1.23): cifras, texto de reglas, acceso, el
timer y los dos contadores de la IA (tiempo y hábitos comparten uno)."""
import json
from datetime import date, timedelta

from sqlmodel import Session, select

from backend.database import engine
from backend.models import User
from backend.reports import missing_reports
from test_finance import maker_on
from test_metrics import MON, TUE, WED, THU, FRI, SAT, SUN, post
from test_report_ai import PLAIN, grant, provider  # noqa: F401  (fixture)

TODAY = date.today()


def generate(api, kind, start, expect=200):
    return api.call("POST", "/api/reports", {"kind": kind, "period_start": start.isoformat(),
                                             "today": TODAY.isoformat()}, expect=expect)[1]


def habits_week(api, email="habitos@test.com"):
    """Gym hecho lunes, martes, miércoles y viernes de la semana pasada; el domingo es de descanso."""
    api.login(email)
    api.call("PATCH", "/api/auth/me", {"rest_days": [6]}, expect=200)
    api.call("POST", "/api/habits/definitions", {"key": "gym", "label": "Gym", "icon": "🏋"}, expect=201)
    api.call("POST", "/api/habits/definitions", {"key": "lectura", "label": "Lectura"}, expect=201)
    for day in (MON, TUE, WED, FRI):
        api.call("PATCH", f"/api/habits/day/{day}", {"habit_key": "gym", "done": True}, expect=200)


# ==================== Hábitos ====================

def test_habits_report(api):
    habits_week(api)
    rep = generate(api, "habits-week", MON)
    assert rep["subject"] == "habits" and rep["through"] == SUN.isoformat()
    m = rep["metrics"]
    gym = next(h for h in m["habits"] if h["key"] == "gym")
    # Lunes a sábado contaban (el domingo es de descanso): 4 de 6
    assert gym["days_done"] == 4 and gym["days_possible"] == 6 and gym["pct"] == 67
    # Lectura es de hoy y no tiene registros antes: la semana pasada no contaba
    lectura = next(h for h in m["habits"] if h["key"] == "lectura")
    assert lectura["days_possible"] == 0 and lectura["pct"] is None
    assert m["missed_days"] == [THU.isoformat(), SAT.isoformat()]
    assert m["off_days"] == [{"date": SUN.isoformat(), "reason": "descanso"}]
    assert m["completion_pct"] == 67 and m["active_days"] == 4 and m["counted_days"] == 6
    # Al cierre de la semana pasada el sábado quedó sin nada: la racha se cortó ahí
    assert m["streak"] == 0 and m["best_streak"] == 3
    assert m["previous"]["completion_pct"] is None   # la semana anterior no tenía nada
    text = rep["text"]
    assert "67 %" in text["summary"] and "descanso" in text["data_cleanup"]
    everything = json.dumps(text, ensure_ascii=False).lower()
    assert "rompiste" not in everything and "fracas" not in everything
    assert rep["headline"] == "67 % de cumplimiento"
    # En la lista, junto a los de tiempo, con su tema
    _, listing = api.call("GET", "/api/reports", expect=200)
    assert [(r["kind"], r["subject"]) for r in listing["reports"]] == [("habits-week", "habits")]


def test_habits_month_has_weeks(api):
    habits_week(api)
    start = MON.replace(day=1)
    rep = generate(api, "habits-month", start)
    weeks = rep["metrics"]["by_week"]
    assert weeks[0]["start"] == start.isoformat()
    assert sum(w["done"] for w in weeks) == rep["metrics"]["done_total"]


def test_habits_and_time_reports_of_a_period_coexist(api):
    habits_week(api)
    _, project = api.call("POST", "/api/projects", {"name": "Tesis"}, expect=201)
    post(api, project, None, MON, 9, 60)
    time_rep = generate(api, "week", MON)
    habits_rep = generate(api, "habits-week", MON)
    assert time_rep["id"] != habits_rep["id"]
    assert time_rep["subject"] == "time" and time_rep["headline"] == "1h 00m"


def test_timer_generates_habit_reports_only_with_the_module(api):
    habits_week(api)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "habitos@test.com")).one()
        assert ("habits-week", MON) in missing_reports(session, user, TODAY)
    api.call("PUT", "/api/auth/me/modules/habits", {"enabled": False}, expect=200)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == "habitos@test.com")).one()
        assert not [k for k, _ in missing_reports(session, user, TODAY) if k.startswith("habits")]


# ==================== Costos ====================

def costs_setup(api, email="costos-rep@test.com"):
    api.login(email)
    maker_on(api, email)
    _, p = api.call("POST", "/api/projects", {"name": "Lámpara"}, expect=201)
    api.call("PUT", f"/api/projects/{p['id']}/finance",
             {"hourly_rate_cents": 30000, "budget_cents": 100000, "kind": "service", "price_cents": 150000}, expect=200)
    _, cats = api.call("GET", "/api/costs/categories", expect=200)
    cat = cats["categories"][0]
    api.call("POST", "/api/costs", {"project_id": p["id"], "category_id": cat["id"], "cost_date": TODAY.isoformat(),
                                    "concept": "Foco", "quantity": 2, "unit_cost_cents": 12550}, expect=201)
    post(api, p, None, TODAY, 9, 60)       # 1 h a 300 = 30000
    return p, cat


def test_costs_report_needs_the_maker_plan(api):
    api.login("sinmaker@test.com")
    assert api.call("POST", "/api/reports", {"kind": "costs-month", "period_start": TODAY.replace(day=1).isoformat(),
                                             "today": TODAY.isoformat()})[0] == 403


def test_costs_report(api):
    p, cat = costs_setup(api)
    rep = generate(api, "costs-month", TODAY.replace(day=1))
    m = rep["metrics"]
    assert rep["subject"] == "costs"
    [row] = m["projects"]
    assert row["labor_cents"] == 30000 and row["costs_cents"] == 25100 and row["total_cost_cents"] == 55100
    assert row["to_date"]["budget_left_cents"] == 100000 - 55100
    assert row["to_date"]["margin_cents"] == 150000 - 55100
    assert m["currencies"] == [{"currency": "MXN", "labor_cents": 30000, "costs_cents": 25100,
                                "total_cost_cents": 55100, "budget_cents": 100000}]
    assert m["top_costs"][0]["concept"] == "Foco" and m["top_costs"][0]["cents"] == 25100
    assert "$551.00 MXN" in rep["text"]["summary"]
    assert any("margen" in item for item in rep["text"]["observations"])
    assert rep["headline"] == "$551.00 MXN"
    # Turning the plan off blocks it again, also for rewriting
    api.call("PUT", "/api/auth/me/modules/maker", {"enabled": False}, expect=200)
    assert api.call("POST", f"/api/reports/{rep['id']}/rewrite")[0] == 403


def test_costs_summary_by_dates(api):
    p, cat = costs_setup(api)
    old = TODAY - timedelta(days=40)
    api.call("POST", "/api/costs", {"project_id": p["id"], "category_id": cat["id"], "cost_date": old.isoformat(),
                                    "concept": "Viejo", "unit_cost_cents": 1000}, expect=201)
    _, everything = api.call("GET", "/api/costs/summary", expect=200)
    _, recent = api.call("GET", f"/api/costs/summary?date_from={(TODAY - timedelta(days=5)).isoformat()}", expect=200)
    assert everything["projects"][0]["costs_cents"] == 26100
    assert recent["projects"][0]["costs_cents"] == 25100


# ==================== Los contadores de la IA ====================

def test_time_and_habits_share_a_counter_costs_has_its_own(api, provider, monkeypatch):  # noqa: F811
    monkeypatch.setenv("AI_COSTS_DAILY_LIMIT", "1")
    monkeypatch.setenv("REPORT_COOLDOWN_SECONDS", "0")
    provider["reply"] = json.dumps(PLAIN, ensure_ascii=False)
    costs_setup(api, "ia-costos@test.com")
    habits_week(api, "ia-costos@test.com")
    grant("ia-costos@test.com")

    assert generate(api, "habits-week", MON)["text_source"] == "ai"
    first = generate(api, "costs-month", TODAY.replace(day=1))
    assert first["text_source"] == "ai"
    again = generate(api, "costs-month", TODAY.replace(day=1))
    assert again["text_source"] == "rules" and "costos" in again["text_note"]

    _, time_usage = api.call("GET", "/api/reports/ai-usage?subject=habits", expect=200)
    _, costs_usage = api.call("GET", "/api/reports/ai-usage?subject=costs", expect=200)
    assert (time_usage["pool"], time_usage["used_today"], time_usage["limit"]) == ("report", 1, 3)
    assert (costs_usage["pool"], costs_usage["used_today"], costs_usage["remaining"]) == ("costs", 1, 0)
    assert api.call("GET", "/api/reports/ai-usage?subject=otra")[0] == 422
    # Each subject sends its own instructions
    assert provider["sent"][0]["report"] == "habits" and provider["sent"][1]["report"] == "costs"
    assert "total_cost_amount" in json.dumps(provider["sent"][1])
