"""
El reporte mensual de costos (plan Maker, 1.23): las cifras que se congelan al
generarlo y su texto con reglas. Se guarda en la tabla `reports` con kind
"costs-month" (backend/report_kinds.py) y se pide desde la pestaña Costos.

Dos miradas, las dos con costs_summary() de backend/costing.py para que cuadren
con la pestaña:
- el mes: horas, mano de obra y gastos con fecha dentro del mes;
- lo acumulado hasta el cierre del mes ("to_date"): el presupuesto disponible y
  el margen, que son del proyecto entero, no de un mes.
Nunca se suman monedas distintas: los totales van por moneda.
"""
from datetime import date as date_type, timedelta
from typing import List, Optional

from sqlmodel import Session, select

from backend.costing import costs_summary, line_total_cents
from backend.models import CostCategory, PomodoroSession, ProjectCost, ProjectFinance, User

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
TOP_COSTS = 8
# Un proyecto con menos de esto de presupuesto disponible merece un aviso
LOW_BUDGET_PCT = 20
SIMILAR_RATIO = 0.10
MAX_ITEMS = 6


def money(cents: Optional[int], currency: str) -> str:
    """$12,300.50 MXN (con signo menos si es negativo)"""
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f} {currency}"


def cost_metrics(session: Session, user: User, start: date_type, end: date_type, today: date_type,
                 with_previous: bool = True) -> dict:
    """Las cifras del reporte de costos del mes [start, end]."""
    through = min(end, today)
    month = costs_summary(session, user.id, start, through)
    to_date = {row.project_id: row for row in costs_summary(session, user.id, None, through).projects}
    category_names = {c.id: c.name for c in session.exec(
        select(CostCategory).where(CostCategory.user_id == user.id)).all()}

    projects = []
    for row in month.projects:
        if not row.total_seconds and not row.costs_cents:
            continue
        acc = to_date.get(row.project_id)
        projects.append({
            "project_id": row.project_id, "name": row.name, "color": row.color, "currency": row.currency,
            "kind": row.kind, "total_seconds": row.total_seconds, "hourly_rate_cents": row.hourly_rate_cents,
            "labor_cents": row.labor_cents, "costs_cents": row.costs_cents, "total_cost_cents": row.total_cost_cents,
            "categories": [{"name": category_names.get(c["category_id"], "Sin categoría"), "cents": c["cents"]}
                           for c in row.categories],
            "to_date": {
                "total_cost_cents": acc.total_cost_cents if acc else row.total_cost_cents,
                "budget_cents": acc.budget_cents if acc else None,
                "budget_left_cents": acc.budget_left_cents if acc else None,
                "price_cents": acc.price_cents if acc else None,
                "margin_cents": acc.margin_cents if acc else None,
            },
        })
    projects.sort(key=lambda p: (p["currency"], -p["total_cost_cents"], p["name"]))
    currencies_used = {p["currency"] for p in projects}

    costs = session.exec(select(ProjectCost).where(
        ProjectCost.user_id == user.id, ProjectCost.cost_date >= start, ProjectCost.cost_date <= through)).all()
    names = {p["project_id"]: (p["name"], p["currency"]) for p in projects}
    top = sorted(costs, key=lambda c: -line_total_cents(c.quantity, c.unit_cost_cents))[:TOP_COSTS]

    metrics = {
        "date_from": start.isoformat(), "date_to": end.isoformat(), "through": through.isoformat(),
        "today": today.isoformat(),
        # Por moneda, con las horas de sus proyectos (para la tabla contra el mes anterior)
        "currencies": [{**t.model_dump(), "total_seconds": sum(p["total_seconds"] for p in projects
                                                               if p["currency"] == t.currency)}
                       for t in month.totals if t.currency in currencies_used],
        "projects": projects,
        "categories": [{"name": c.name, "color": c.color, "currency": c.currency, "cents": c.cents}
                       for c in month.categories],
        "top_costs": [{"date": c.cost_date.isoformat(), "concept": c.concept,
                       "project": names.get(c.project_id, ("", ""))[0],
                       "category": category_names.get(c.category_id, "Sin categoría"),
                       "currency": names.get(c.project_id, ("", "MXN"))[1],
                       "cents": line_total_cents(c.quantity, c.unit_cost_cents)}
                      for c in top if c.project_id in names],
        "no_rate": [p["name"] for p in projects if p["total_seconds"] and p["hourly_rate_cents"] is None],
        "previous": None,
    }
    if with_previous:
        prev_end = start - timedelta(days=1)
        prev = cost_metrics(session, user, prev_end.replace(day=1), prev_end, today, with_previous=False)
        metrics["previous"] = {
            "date_from": prev["date_from"], "date_to": prev["date_to"],
            "currencies": prev["currencies"],
            "projects": [{"name": p["name"], "color": p["color"], "currency": p["currency"],
                          "total_cost_cents": p["total_cost_cents"]} for p in prev["projects"]],
            "project_count": len(prev["projects"]),
        }
    return metrics


def has_cost_activity(session: Session, user_id: int, start: date_type, end: date_type) -> bool:
    """¿Hubo gastos, o tiempo en un proyecto con costeo, en el periodo?"""
    if session.exec(select(ProjectCost.id).where(
            ProjectCost.user_id == user_id, ProjectCost.cost_date >= start,
            ProjectCost.cost_date <= end).limit(1)).first() is not None:
        return True
    costed = select(ProjectFinance.project_id).where(ProjectFinance.user_id == user_id)
    return session.exec(select(PomodoroSession.id).where(
        PomodoroSession.user_id == user_id, PomodoroSession.mode == "focus",
        PomodoroSession.session_date >= start, PomodoroSession.session_date <= end,
        PomodoroSession.project_id.in_(costed)).limit(1)).first() is not None


# ============================================
# El texto, con reglas
# ============================================

def _month_name(iso: str) -> str:
    return MONTHS[date_type.fromisoformat(iso).month - 1]


def _join(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def _hours(seconds: int) -> str:
    value = round((seconds or 0) / 3600, 1)
    return "0 h" if value == 0 else f"{value:.1f} h"


def _prev_total(m: dict, currency: str) -> Optional[int]:
    for t in ((m.get("previous") or {}).get("currencies") or []):
        if t["currency"] == currency:
            return t["total_cost_cents"]
    return None


def _summary(m: dict) -> str:
    parts = []
    for t in m["currencies"]:
        cur = t["currency"]
        piece = f"En {cur}, {_month_name(m['date_from'])} te costó {money(t['total_cost_cents'], cur)}"
        detail = []
        if t["labor_cents"]:
            detail.append(f"{money(t['labor_cents'], cur)} de mano de obra")
        if t["costs_cents"]:
            detail.append(f"{money(t['costs_cents'], cur)} de gastos")
        if detail:
            piece += f" ({_join(detail)})"
        prev = _prev_total(m, cur)
        if prev:
            change = (t["total_cost_cents"] - prev) / prev
            if abs(change) < SIMILAR_RATIO:
                piece += f", parecido al mes anterior ({money(prev, cur)})"
            else:
                piece += f", {'más' if change > 0 else 'menos'} que el mes anterior ({money(prev, cur)})"
        parts.append(piece + ".")
    if m["through"] < m["date_to"]:
        parts.append(f"El mes sigue en curso: cuenta hasta el {date_type.fromisoformat(m['through']).day}.")
    return " ".join(parts)


def _cleanup(m: dict) -> str:
    if not m["no_rate"]:
        return ""
    return (f"Ojo: {_join(m['no_rate'])} {'tiene' if len(m['no_rate']) == 1 else 'tienen'} horas sin tarifa, "
            f"así que su mano de obra no se cuenta.")


def _patterns(m: dict) -> List[str]:
    out = []
    for cur in [t["currency"] for t in m["currencies"]]:
        rows = [p for p in m["projects"] if p["currency"] == cur and p["total_cost_cents"]]
        if rows:
            top = rows[0]
            out.append(f"{top['name']} fue el proyecto que más costó: {money(top['total_cost_cents'], cur)}"
                       + (f" con {_hours(top['total_seconds'])} de trabajo." if top["total_seconds"] else "."))
        cats = [c for c in m["categories"] if c["currency"] == cur]
        if cats:
            out.append(f"El gasto más grande por categoría fue {cats[0]['name']}: {money(cats[0]['cents'], cur)}.")
    if m["top_costs"]:
        c = m["top_costs"][0]
        out.append(f"El gasto más grande: {c['concept']} ({c['project']}), {money(c['cents'], c['currency'])}.")
    return out[:MAX_ITEMS]


def _observations(m: dict) -> List[str]:
    over, low, loss, gain = [], [], [], []
    for p in m["projects"]:
        acc, cur = p["to_date"], p["currency"]
        if acc["budget_left_cents"] is not None and acc["budget_cents"]:
            if acc["budget_left_cents"] < 0:
                over.append(f"{p['name']} ya pasó su presupuesto por {money(-acc['budget_left_cents'], cur)}.")
            elif acc["budget_left_cents"] * 100 < acc["budget_cents"] * LOW_BUDGET_PCT:
                low.append(f"A {p['name']} le quedan {money(acc['budget_left_cents'], cur)} de presupuesto.")
        if acc["margin_cents"] is not None and p["kind"] != "personal":
            if acc["margin_cents"] < 0:
                loss.append(f"{p['name']} va con pérdida: {money(-acc['margin_cents'], cur)} "
                            f"(cobras {money(acc['price_cents'], cur)}).")
            else:
                gain.append(f"{p['name']} lleva un margen de {money(acc['margin_cents'], cur)} "
                            f"de {money(acc['price_cents'], cur)}.")
    return (over + loss + low + gain)[:MAX_ITEMS]


def _comparison(m: dict) -> str:
    pieces = []
    for t in m["currencies"]:
        prev = _prev_total(m, t["currency"])
        if prev is not None:
            pieces.append(f"{money(t['total_cost_cents'], t['currency'])} este mes frente a "
                          f"{money(prev, t['currency'])} el anterior")
    return f"Costo total: {_join(pieces)}." if pieces else ""


def _next_steps(m: dict) -> List[str]:
    out = []
    if m["no_rate"]:
        out.append(f"Ponle tarifa a {_join(m['no_rate'])} para ver cuánto vale tu tiempo ahí.")
    for p in m["projects"]:
        acc = p["to_date"]
        if acc["budget_left_cents"] is not None and acc["budget_left_cents"] < 0:
            out.append(f"Revisa el alcance o el presupuesto de {p['name']}.")
        elif p["kind"] in ("product", "service") and acc["price_cents"] is None:
            out.append(f"Anota el precio de {p['name']} para ver su margen.")
    if not out:
        out.append("Sigue registrando tus gastos el mismo día: así el reporte del próximo mes sale completo.")
    return out[:4]


def _closing(m: dict) -> dict:
    gains = [p for p in m["projects"] if (p["to_date"]["margin_cents"] or 0) > 0 and p["kind"] != "personal"]
    if gains:
        well = f"{gains[0]['name']} mantiene un margen positivo."
    elif m["top_costs"] or any(p["total_seconds"] for p in m["projects"]):
        well = "Tienes tus costos del mes registrados y comparables."
    else:
        well = ""
    return {"well_done": well,
            "tip": "Separa en una categoría los gastos que se repiten cada mes: ayuda a ver tu costo fijo."}


def build_costs_text(m: dict) -> dict:
    """La misma forma que el texto del reporte de tiempo (report_text.build_text)."""
    if not m["projects"]:
        return {"summary": f"No hubo gastos ni tiempo en proyectos con costeo en {_month_name(m['date_from'])}.",
                "data_cleanup": "", "patterns": [], "legibility": [], "observations": [], "comparison": "",
                "next_steps": [], "closing": {"well_done": "", "tip": "Cuando registres gastos o tiempo, "
                                                                         "este reporte mostrará en qué se fue el dinero."}}
    return {
        "summary": _summary(m),
        "data_cleanup": _cleanup(m),
        "patterns": _patterns(m),
        "legibility": [],
        "observations": _observations(m),
        "comparison": _comparison(m),
        "next_steps": _next_steps(m),
        "closing": _closing(m),
    }
