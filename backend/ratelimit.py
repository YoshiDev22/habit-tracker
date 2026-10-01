"""
Límite de intentos en memoria, para login y registro.

Sin dependencias ni tabla: la app corre en un solo proceso de uvicorn, y
perder los contadores al reiniciar no importa (solo alargan una espera de
minutos). Con varios workers cada uno llevaría su cuenta y el límite real
se multiplicaría por su número.

La clave es la IP del cliente. Detrás de Caddy, uvicorn la toma de
X-Forwarded-For solo si la conexión viene de una IP en --forwarded-allow-ips
(por defecto 127.0.0.1). Si Caddy llegara por otra (::1, una red de Docker),
todos los usuarios compartirían la IP del proxy y el límite de uno frenaría a
todos: ver "Producción" en CLAUDE.md.
"""
import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request, status

# Por encima de estas claves se barren las que ya no tienen intentos vivos,
# para que muchas IPs distintas no hagan crecer la memoria sin fin
MAX_KEYS = 10_000


class SlidingWindow:
    """Como mucho `limit` eventos por clave en los últimos `window` segundos."""

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: Dict[str, Deque[float]] = {}
        # Los endpoints síncronos de FastAPI corren en un pool de hilos
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if not hits:
            del self._hits[key]
        return hits

    def retry_after(self, key: str) -> Optional[int]:
        """Segundos hasta que la clave pueda volver a intentar, o None si puede ya."""
        with self._lock:
            now = time.monotonic()
            hits = self._prune(key, now)
            if len(hits) < self.limit:
                return None
            return max(1, int(hits[0] + self.window - now) + 1)

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            if len(self._hits) >= MAX_KEYS:
                for stale in list(self._hits):
                    self._prune(stale, now)
            self._hits.setdefault(key, deque()).append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Contraseñas equivocadas: 10 cada 15 minutos por IP. Sobra para quien se
# equivoca, y a fuerza bruta son ~1000 intentos al día en vez de miles por minuto.
failed_logins = SlidingWindow(limit=10, window=15 * 60)
# Cuentas creadas: 5 por hora por IP. Frena el registro en masa sin estorbar
# a quien crea una cuenta de prueba.
registrations = SlidingWindow(limit=5, window=60 * 60)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def ensure_allowed(window: SlidingWindow, key: str, message: str) -> None:
    """429 con Retry-After si la clave agotó sus intentos."""
    wait = window.retry_after(key)
    if wait is not None:
        minutes = max(1, (wait + 59) // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"{message} Vuelve a intentarlo en {minutes} min.",
            headers={"Retry-After": str(wait)},
        )


def reset_all() -> None:
    """Para las pruebas: cada una empieza sin intentos contados."""
    failed_logins.reset()
    registrations.reset()
