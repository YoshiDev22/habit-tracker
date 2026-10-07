"""
Los tipos de reporte guardado (1.23). Cada `kind` de la tabla `reports` dice de
qué es (tiempo, hábitos o costos) y de qué periodo (semana o mes):

    week · month                   tiempo (desde la 1.20)
    habits-week · habits-month     hábitos
    costs-month                    costos (plan Maker)

Va en el kind, no en una columna aparte, porque la restricción única de la tabla
es (usuario, kind, inicio): así cada tema tiene su reporte por periodo sin
migrar. Sin dependencias: lo importan schemas.py y los módulos de reportes.
"""
from typing import Optional

KINDS = ("week", "month", "habits-week", "habits-month", "costs-month")

# El contador de textos con IA de cada tema (AiCall.purpose): tiempo y hábitos
# comparten el de "report"; costos lleva el suyo
AI_POOL = {"time": "report", "habits": "report", "costs": "costs"}

# El módulo que debe estar encendido para que el timer genere los de un tema
MODULE = {"time": None, "habits": "habits", "costs": "maker"}


def subject_of(kind: str) -> str:
    """time | habits | costs"""
    return kind.split("-", 1)[0] if "-" in kind else "time"


def period_of(kind: str) -> str:
    """week | month"""
    return kind.split("-", 1)[1] if "-" in kind else kind


def kind_for(subject: str, period: str) -> Optional[str]:
    kind = period if subject == "time" else f"{subject}-{period}"
    return kind if kind in KINDS else None
