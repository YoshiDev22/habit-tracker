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
MAX_SUMMARY = 700
MAX_ITEM = 400
MAX_OBSERVATIONS = 8
MAX_RECOMMENDATIONS = 6
# Cifras que se pueden escribir sin venir en las métricas: conteos chicos
# ("dos días", "3 recomendaciones") y los umbrales que la app explica
FREE_NUMBERS = set(range(0, 11)) | {16, 23, 24}
NUMBER_RE = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?")

SYSTEM_PROMPT = """Escribes el texto de un reporte personal de productividad: cuánto tiempo trabajó una persona en una semana o un mes, y en qué.

Recibes un JSON con métricas ya calculadas. Las duraciones vienen en minutos. "comparison" compara con el periodo anterior.

Reglas:
1. Escribe en español de México, en segunda persona ("registraste"), con un tono sobrio: describe, no regañes ni celebres de más.
2. Usa SOLO cifras que aparecen en el JSON. Puedes convertir minutos a horas y minutos ("417 minutos" -> "6 h 57 min"), pero no calcules promedios, sumas ni porcentajes nuevos.
3. No inventes causas, datos ni nombres. Usa los nombres de proyectos y tareas tal como vienen.
4. "summary": dos o tres oraciones con lo principal del periodo y la comparación.
5. "observations": de 2 a 6 observaciones concretas, una o dos oraciones cada una.
6. "recommendations": solo si una cifra lo justifica (registros por revisar, días hábiles sin registro, sesiones nocturnas, pomodoros cortados); si no, lista vacía. Máximo 4.
7. "closing": una oración de cierre.

Responde SOLO con un objeto JSON, sin texto antes ni después y sin bloques de código:
{"summary": "...", "observations": ["..."], "recommendations": ["..."], "closing": "..."}"""


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
            if k == "seconds" or k.endswith("_seconds"):
                out[k[:-len("seconds")] + "minutes"] = round(v / 60) if isinstance(v, (int, float)) else v
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

def _numbers_in(text: str) -> Iterable[float]:
    for match in NUMBER_RE.findall(text):
        yield float(match.replace(",", "."))


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
            for n in _numbers_in(value.replace("-", " ").replace(":", " ")):
                allowed.add(n)
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


def _text(value, limit: int, field: str) -> str:
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
    text = {
        "summary": _text(data.get("summary"), MAX_SUMMARY, "summary"),
        "observations": _items(data.get("observations"), MAX_OBSERVATIONS, "observations"),
        "recommendations": _items(data.get("recommendations"), MAX_RECOMMENDATIONS, "recommendations"),
        "closing": _text(data.get("closing"), MAX_ITEM, "closing"),
    }
    allowed = allowed_numbers(payload)
    pieces = [text["summary"], text["closing"], *text["observations"], *text["recommendations"]]
    for piece in pieces:
        for number in _numbers_in(piece):
            if not any(abs(number - a) < 0.051 for a in allowed):
                raise AiError(f"La IA citó una cifra que no venía en las métricas ({number:g})")
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
        reply = chat_completion(config, SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False))
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
