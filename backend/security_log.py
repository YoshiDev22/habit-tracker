"""
Eventos de seguridad (1.27, Fase 2 del panel, paso 8): lo que delata un abuso,
nunca lo que hace cada persona en la app. Los lee el panel de administración
(pestaña Seguridad); complementan a Cloudflare, que ve la red pero no la app.

- Solo se escribe cuando algo falla (o al crear una cuenta, para ver registros
  masivos): un login correcto o una petición normal no escriben nada.
- Agrupado: una fila por hora, tipo, IP y cuenta, con su contador. Un ataque de
  miles de intentos es una fila que sube, no miles de filas.
- La IP completa (sirve para bloquear en Cloudflare o ufw), 30 días (KEEP_DAYS) y
  con user_id: se va con la cuenta (purge_user).
- En su propia sesión, y nunca rompe la petición: si el registro falla, la app
  sigue como si nada.
"""
import ipaddress
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import delete
from sqlmodel import Session, select

from backend.database import engine
from backend.models import SecurityEvent, utc_now_naive

KEEP_DAYS = 30
KINDS = {
    "login_failed": "Contraseña equivocada al entrar",
    "password_failed": "Contraseña equivocada en Mi perfil",
    "login_blocked": "Login bloqueado por el límite de intentos",
    "register": "Cuenta creada",
    "register_blocked": "Registro bloqueado por el límite",
    "token_invalid": "Token inválido o vencido",
    "token_revoked": "Token de una sesión cerrada",
    "account_inactive": "Token de una cuenta desactivada",
    "ai_limit": "Límite de IA alcanzado",
    "feedback_limit": "Límite de reportes de problemas",
    "admin_denied": "Acceso rechazado al panel",
    "admin_csrf": "Cambio rechazado en el panel (CSRF)",
}
MAX_IP = 64
log = logging.getLogger(__name__)


def record(kind: str, ip: Optional[str] = None, user_id: Optional[int] = None) -> None:
    """Suma uno al evento de esta hora. Nunca lanza: un fallo aquí no es del usuario."""
    if kind not in KINDS:
        raise ValueError(f"Evento de seguridad desconocido: {kind}")
    try:
        now = utc_now_naive()
        hour = now.replace(minute=0, second=0, microsecond=0)
        ip = (ip or "")[:MAX_IP]
        with Session(engine) as session:
            query = select(SecurityEvent).where(SecurityEvent.hour == hour, SecurityEvent.kind == kind,
                                                SecurityEvent.ip == ip)
            query = query.where(SecurityEvent.user_id == user_id) if user_id is not None \
                else query.where(SecurityEvent.user_id.is_(None))
            row = session.exec(query).first()
            if row is None:
                row = SecurityEvent(hour=hour, kind=kind, ip=ip, user_id=user_id, count=0)
            row.count += 1
            row.last_at = now
            session.add(row)
            session.commit()
    except Exception:
        log.exception("No se pudo anotar el evento de seguridad %s", kind)


def cleanup(session: Session) -> int:
    """Borra lo que tiene más de KEEP_DAYS días. Hace commit; devuelve cuántas filas."""
    cutoff = utc_now_naive() - timedelta(days=KEEP_DAYS)
    result = session.exec(delete(SecurityEvent).where(SecurityEvent.hour < cutoff))
    session.commit()
    return result.rowcount or 0


# Donde vive un proxy: la misma máquina o la red local. Lista explícita: is_private de
# Python incluye también las redes de documentación (203.0.113.0/24…), que no son proxies
PROXY_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7", "fe80::/10")]


def is_proxy_ip(ip: str) -> bool:
    """La IP de un proxy en la misma máquina o red (Caddy, cloudflared): si casi todo
    llega de una así, la app no está viendo la IP real del cliente."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in PROXY_NETWORKS if address.version == network.version)
