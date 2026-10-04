"""
El texto de un reporte escrito por la IA (épica 30, Fase 5). La IA recibe solo
las cifras ya calculadas (backend/metrics.py), en minutos y sin ids, nunca los
registros crudos, y devuelve la misma forma que backend/report_text.py:
summary, observations, recommendations y closing.

Lo que vuelve se valida antes de guardarlo: JSON con esa forma exacta, textos
con tope, y ninguna cifra que no venga en lo enviado (o en su conversión de
minutos a horas). Si algo falla, el reporte se queda con el texto de las
reglas y dice por qué (Report.text_note). Cada llamada queda en ai_calls, que
es lo que cuenta el límite diario por cuenta.
"""
import json
import re
from datetime import datetime, time, timezone
from typing import Iterable, Optional, Set, Tuple

from sqlmodel import Session, func, select

from backend.ai import AiConfig, AiError, chat_completion
from backend.models import AiCall, User

KIND_NAME = {"week": "semana", "month": "mes"}
DROP_KEYS = {"project_id", "task_id", "tag_id", "session_id", "color", "timezone"}
MAX_SUMMARY = 900
MAX_ITEM = 400
LIST_LIMITS = {"patterns": 6, "legibility": 4, "observations": 6, "next_steps": 5}
# Cifras que se pueden escribir sin venir en las métricas: conteos chicos
# ("dos días", "3 recomendaciones") y los umbrales que la app explica
FREE_NUMBERS = set(range(0, 11)) | {16, 23, 24}
# Un número con separador de miles ("1 580", "1,580", "1.580") va entero: si no,
# se leería como "1" y "580". Si no, entero o con decimales ("6.5", "6,5").
THOUSANDS = r"\d{1,3}(?:[ \u00a0\u202f.,]\d{3})+(?![\d.,]\d)"
NUMBER_RE = re.compile(rf"(?<![\w.,])(?:{THOUSANDS}|\d+(?:[.,]\d+)?)")

SYSTEM_PROMPT = """Escribes el texto de un reporte personal de tiempo de trabajo: cuánto trabajó una persona en una semana o un mes, en qué, y qué conviene cambiar. Lo leerá ella misma.

Recibes un JSON con métricas ya calculadas por la app. Las duraciones vienen en minutos. "previous" es el periodo anterior completo; "comparison", el cambio del total. "days_detail" trae cada día con su estado: worked, missing (hábil sin registro), off (fin de semana, festivo o vacaciones, con su motivo), today (hoy, aún sin tiempo) o pending (todavía no llega). "projected_minutes" es una proyección al cierre si el periodo va a medias. "by_week" son las semanas del mes. "top_tasks" trae sesiones y días de cada tarea. "top_project_tags" es el proyecto principal por etiqueta (una sesión cuenta en cada etiqueta de su tarea: no se suman). "to_review" lista registros dudosos: se cuentan todos, nada se excluye.

Reglas de las cifras:
1. Usa SOLO cifras que aparecen en el JSON. Escribe las horas en decimal con un decimal ("858 minutos" -> "14.3 h") o en horas y minutos. No calcules sumas, promedios ni porcentajes nuevos: si comparas, usa los "pct" de cada periodo.
2. Solo en "next_steps" puedes proponer metas con números enteros nuevos ("Mantén el Habit Tracker en 4 h o menos"), apoyadas en una cifra del JSON.
3. No inventes causas, datos ni nombres. Usa los nombres de proyectos y tareas tal como vienen.

Estilo: español de México, en segunda persona ("llevas", "registraste"), concreto, sobrio y cálido; describe lo que pasó, no regañes ni celebres de más. Frases cortas.

Secciones:
- "summary": un párrafo. Horas y días hábiles con registro (di qué días fueron festivo, cuál sigue en curso o pendiente), horas por día comparadas con el periodo anterior y, si hay proyección, "cerrarías alrededor de X h (estimado)". En un mes, la tendencia por semana.
- "data_cleanup": una oración que empieza con "Limpieza de datos:". Qué hay en to_review y que no se excluyó nada; si hay tiempo sin confirmar, cuánto sería sin él.
- "patterns": de 2 a 5 viñetas: horario promedio y horas después de las 16 h; una tarea que se repite (sesiones en días); días sin registro; descanso (sesiones nocturnas, o que no te desvelaste); pomodoros o registro a mano si destacan.
- "legibility": de 0 a 3 viñetas sobre tareas con nombres poco descriptivos ("Ajustes", "Tarea 08/09") y el uso de etiquetas. Vacía si no hay nada.
- "observations": de 2 a 5 viñetas comparando con el periodo anterior (cómo cambió el % de cada proyecto) y lo que llame la atención.
- "comparison": solo en un mes: una o dos oraciones contra el mes anterior; en una semana, cadena vacía.
- "next_steps": de 1 a 4 viñetas accionables para el siguiente periodo, con metas medibles cuando se pueda.
- "closing": {"well_done": un logro concreto del periodo, "tip": un consejo concreto y breve}.

Responde SOLO con un objeto JSON, sin texto antes ni después y sin bloques de código:
{"summary": "...", "data_cleanup": "...", "patterns": ["..."], "legibility": [], "observations": ["..."], "comparison": "", "next_steps": ["..."], "closing": {"well_done": "...", "tip": "..."}}"""


# ============================================
# Lo que se envía
# ============================================

def _clock(hours: float) -> str:
    total = round(hours * 60)
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def _compact(value, key: str = ""):
    """Copia sin ids ni colores, con los segundos pasados a minutos."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in DROP_KEYS:
                continue
            # total_seconds, avg_seconds_per_active_day, seconds_after_16h...
            if "seconds" in k and (isinstance(v, (int, float)) or v is None):
                out[k.replace("seconds", "minutes")] = round(v / 60) if v is not None else None
            else:
                out[k] = _compact(v, k)
        return out
    if isinstance(value, list):
        return [_compact(v, key) for v in value]
    return value


def ai_payload(kind: str, metrics: dict) -> dict:
    """El JSON exacto que se manda (y el que muestra "Ver qué se envía")."""
    m = _compact({k: v for k, v in metrics.items() if k != "by_source"})
    if metrics.get("schedule"):
        m["schedule"] = {"usual_start": _clock(metrics["schedule"]["usual_start"]),
                         "usual_end": _clock(metrics["schedule"]["usual_end"])}
    previous = metrics.get("previous") or {}
    prev_total = previous.get("total_seconds") or 0
    comparison = {"previous_total_minutes": round(prev_total / 60)}
    if prev_total:
        comparison["change_pct"] = round((metrics["total_seconds"] - prev_total) * 100 / prev_total)
        comparison["difference_minutes"] = round(abs(metrics["total_seconds"] - prev_total) / 60)
    m["comparison"] = comparison
    return {"period": KIND_NAME[kind], "metrics": m}


# ============================================
# Lo que vuelve
# ============================================

def _readings(match: str) -> Set[float]:
    """Las formas de leer un número escrito: "1,580" puede ser 1580 o 1.58."""
    readings = set()
    if re.fullmatch(THOUSANDS, match):
        readings.add(float(re.sub(r"\D", "", match)))
    if re.fullmatch(r"\d+(?:[.,]\d+)?", match):
        readings.add(float(match.replace(",", ".")))
    return readings


def _numbers_in(text: str) -> Iterable[Set[float]]:
    for match in NUMBER_RE.findall(text):
        yield _readings(match)


def allowed_numbers(payload: dict) -> Set[float]:
    """Toda cifra que el texto puede citar: las del JSON, sus minutos en horas
    y minutos, las partes de sus fechas y horas, y las de nombres y títulos."""
    allowed: Set[float] = set(float(n) for n in FREE_NUMBERS)

    def walk(value, key=""):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            allowed.add(float(value))
            allowed.add(float(abs(value)))
            if key.endswith("minutes"):
                minutes = abs(int(value))
                allowed.update({float(minutes // 60), float(minutes % 60),
                                round(minutes / 60, 1), float(round(minutes / 60))})
        elif isinstance(value, str):
            for readings in _numbers_in(value.replace("-", " ").replace(":", " ")):
                allowed.update(readings)
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)

    walk(payload)
    return allowed


def _extract_json(content: str) -> dict:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise AiError("La IA no respondió un JSON")
    try:
        data = json.loads(content[start:end + 1])
    except ValueError:
        raise AiError("La IA respondió un JSON inválido") from None
    if not isinstance(data, dict):
        raise AiError("La IA no respondió un objeto JSON")
    return data


def _text(value, limit: int, field: str, allow_empty: bool = False) -> str:
    if allow_empty and value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip():
        raise AiError(f"La IA dejó vacío «{field}»")
    value = " ".join(value.split())
    if len(value) > limit:
        raise AiError(f"La IA escribió de más en «{field}»")
    return value


def _items(value, limit: int, field: str) -> list:
    if not isinstance(value, list) or len(value) > limit:
        raise AiError(f"La IA no respetó la lista «{field}»")
    return [_text(item, MAX_ITEM, field) for item in value]


def validate_text(content: str, payload: dict) -> dict:
    """El texto listo para guardar, o AiError si no se puede confiar en él."""
    data = _extract_json(content)
    closing = data.get("closing")
    if not isinstance(closing, dict):
        raise AiError("La IA no respetó «closing»")
    text = {
        "summary": _text(data.get("summary"), MAX_SUMMARY, "summary"),
        "data_cleanup": _text(data.get("data_cleanup"), MAX_ITEM, "data_cleanup"),
        **{field: _items(data.get(field), limit, field) for field, limit in LIST_LIMITS.items()},
        "comparison": _text(data.get("comparison"), MAX_ITEM, "comparison", allow_empty=True),
        "closing": {"well_done": _text(closing.get("well_done"), MAX_ITEM, "well_done"),
                    "tip": _text(closing.get("tip"), MAX_ITEM, "tip")},
    }
    allowed = allowed_numbers(payload)
    facts = [text["summary"], text["data_cleanup"], text["comparison"], *text["patterns"],
             *text["legibility"], *text["observations"], text["closing"]["well_done"], text["closing"]["tip"]]

    def check(piece: str, targets_ok: bool) -> None:
        for readings in _numbers_in(piece):
            if any(abs(number - a) < 0.051 for number in readings for a in allowed):
                continue
            # Una meta puede proponer un entero nuevo ("4 h o menos"), no un decimal
            if targets_ok and any(number == int(number) for number in readings):
                continue
            raise AiError(f"La IA citó una cifra que no venía en las métricas ({max(readings):g})")

    for piece in facts:
        check(piece, targets_ok=False)
    for piece in text["next_steps"]:
        check(piece, targets_ok=True)
    return text


# ============================================
# La llamada, con su límite diario
# ============================================

def calls_today(session: Session, user_id: int) -> int:
    midnight = datetime.combine(datetime.now(timezone.utc).date(), time(0))
    return session.exec(select(func.count(AiCall.id)).where(
        AiCall.user_id == user_id, AiCall.created_at >= midnight)).one()


def write_with_ai(session: Session, user: User, kind: str, metrics: dict, config: AiConfig) -> Tuple[dict, str]:
    """(texto, modelo), o AiError. Cada intento cuenta para el límite del día."""
    if calls_today(session, user.id) >= config.daily_limit:
        raise AiError(f"Llegaste al límite de {config.daily_limit} textos con IA por hoy")
    payload = ai_payload(kind, metrics)
    call = AiCall(user_id=user.id, model=config.model)
    try:
        reply = chat_completion(config, SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False), max_tokens=8000)
        call.input_tokens, call.output_tokens = reply.input_tokens, reply.output_tokens
        text = validate_text(reply.content, payload)
        call.ok = True
        return text, config.model
    except AiError as error:
        call.error = str(error)[:200]
        raise
    finally:
        session.add(call)
        session.commit()


def ai_preview(kind: str, metrics: Optional[dict]) -> dict:
    """Lo que vería el proveedor: las instrucciones y el JSON del periodo."""
    return {"system": SYSTEM_PROMPT, "payload": ai_payload(kind, metrics) if metrics else None}
