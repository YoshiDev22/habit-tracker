"""
El aviso de privacidad (1.28, BACKLOG 39): privacidad.html con los datos de esta
instancia. El texto describe lo que hace el código, igual para cualquier instalación;
quién responde y con qué proveedores corre es de cada una y va en backend/.env, no en
el repo (que es público). Plan y razones: docs/specs/aviso-privacidad.md.

  PRIVACY_EMAIL    correo para el responsable y los derechos ARCO
  PRIVACY_HOSTING  dónde vive el servidor ("Proveedor (servidor en País)")
  PRIVACY_BACKUPS  opcional: dónde se guardan además las copias de respaldo ("Un servicio de almacenamiento")
  PRIVACY_PROXY    opcional: la red delante de la app ("Cloudflare")
  PRIVACY_AI       opcional: el proveedor de IA y lo que dice del contenido

Se lee en cada petición: cambiar el .env basta con reiniciar el servicio, como todo.
"""
import html
import os
import re
from datetime import date

# Cambia con el texto: va en el mismo commit que lo cambie (y el aviso 📢 se publica aparte)
UPDATED = date(2026, 10, 18)
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre")
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "privacidad.html")


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _block(text: str, name: str, keep: bool) -> str:
    """Un bloque <!--name-->…<!--/name-->: sin las marcas si se queda, entero fuera si no."""
    pattern = re.compile(rf"<!--{name}-->(.*?)<!--/{name}-->", re.S)
    return pattern.sub(lambda m: m.group(1) if keep else "", text)


def render() -> str:
    from backend.ai import ai_config   # aquí: el aviso no debe frenar el arranque de nada

    page = open(TEMPLATE, encoding="utf-8").read()
    email, hosting, backups, proxy, ai = (_env(n) for n in ("PRIVACY_EMAIL", "PRIVACY_HOSTING", "PRIVACY_BACKUPS",
                                                             "PRIVACY_PROXY", "PRIVACY_AI"))
    if not ai and ai_config() is not None:
        ai = "el proveedor de IA de esta instalación"
    page = _block(page, "backups", bool(backups))
    page = _block(page, "proxy", bool(proxy))
    page = _block(page, "ai", bool(ai))

    missing = ('<p class="privacy-missing">Esta instalación aún no tiene un contacto de privacidad '
               'configurado (<code>PRIVACY_EMAIL</code> en <code>backend/.env</code>).</p>') if not email else ""
    email_html = (f'<a href="mailto:{html.escape(email, quote=True)}">{html.escape(email)}</a>'
                  if email else "<strong>[contacto sin configurar]</strong>")
    ip_logs = (f"El servidor y {html.escape(proxy)} también registran la IP de cada visita." if proxy
               else "El servidor también registra la IP de cada visita.")
    values = {
        "UPDATED": f"{UPDATED.day} de {MONTHS[UPDATED.month - 1]} de {UPDATED.year}",
        "MISSING": missing,
        "EMAIL": email_html,
        "IP_LOGS": ip_logs,
        "HOSTING": html.escape(hosting) if hosting else "el proveedor del servidor",
        "BACKUPS": html.escape(backups),
        "PROXY": html.escape(proxy),
        "AI": html.escape(ai),
    }
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], page)
