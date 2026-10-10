"""
Las reglas de los avisos para todas las cuentas (1.27, Fase 2 del panel, paso 6).
Las usan el panel (backend/admin_api.py) y scripts/announce.py, para que nunca
se contradigan. Solo biblioteca estándar: announce.py corre con un python3
pelado en el VPS, igual que migrate.py y grant_module.py.
"""
from datetime import datetime, timedelta
from typing import Optional

MAX_TITLE = 80
MAX_BODY = 500
MAX_CURRENT = 3            # vigentes a la vez: que la campanita no se llene
COOLDOWN_SECONDS = 30      # entre dos publicaciones: un doble clic no publica dos veces


def check(title: str, body: str, current: int, last_created: Optional[datetime], now: datetime) -> Optional[str]:
    """El motivo por el que no se puede publicar, o None. `current` son los vigentes y
    `last_created` cuándo se publicó el último (UTC naive)."""
    if not title.strip():
        return "Falta el título"
    if len(title.strip()) > MAX_TITLE or len(body.strip()) > MAX_BODY:
        return f"Título hasta {MAX_TITLE} caracteres y texto hasta {MAX_BODY}"
    if current >= MAX_CURRENT:
        return f"Ya hay {current} avisos vigentes (como mucho {MAX_CURRENT}): termina uno antes"
    if last_created is not None and now - last_created < timedelta(seconds=COOLDOWN_SECONDS):
        return f"Acabas de publicar uno: espera {COOLDOWN_SECONDS} s para publicar otro"
    return None
