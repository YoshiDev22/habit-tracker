"""
Módulos que cada cuenta puede usar (épica 24, docs/specs/modulos-y-costeo.md).

El Núcleo (tableros, tiempo, Reportes) no está aquí: es de todos, siempre.
Apagar un módulo oculta su parte de la app y no borra nada.

Sin dependencias, ni siquiera sqlmodel: scripts/grant_module.py lo importa con
un python3 pelado en el VPS, igual que migrate.py.
"""

# Lo que vale cuando la cuenta no tiene fila en user_modules:
# - enabled: si está encendido mientras el usuario no elija otra cosa.
# - allowed: si cualquier cuenta puede usarlo, sin que se le dé acceso.
MODULES = {
    # Calendario, racha, escudos y pausas; más adelante, metas (épica 17)
    "habits": {"enabled": True, "allowed": True},
    # Plan maker: costeo de proyectos para freelance y makers. Gratis, pero por
    # ahora solo para las cuentas con acceso (scripts/grant_module.py).
    "maker": {"enabled": False, "allowed": False},
}


def resolve(module, enabled=None, allowed=None):
    """Estado de un módulo para una cuenta, a partir de su fila (NULL = el
    valor por defecto). Sin acceso, el módulo está apagado aunque el usuario
    lo hubiera encendido: quitar el acceso no necesita tocar su preferencia."""
    default = MODULES[module]
    is_allowed = default["allowed"] if allowed is None else bool(allowed)
    is_enabled = default["enabled"] if enabled is None else bool(enabled)
    return {"enabled": is_allowed and is_enabled, "allowed": is_allowed}
