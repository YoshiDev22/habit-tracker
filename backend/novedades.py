"""
Las Novedades de cada versión (1.25): lo que ve quien usa la app al entrar
después de una actualización y en Mi perfil › Novedades. Salen de NOVEDADES.md
(en la raíz), no del CHANGELOG: es un texto propio, corto, para el usuario, sin
nada de despliegue. Se escribe en el mismo commit del bump (CLAUDE.md,
Versionado).

Formato del archivo, una sección por versión, la más nueva arriba:

    ## 1.25.0 — 2026-10-09
    ### Nuevas funciones
    - **Notas por día**: en el calendario, toca ✎ junto a un hábito…
      (una viñeta puede seguir en la línea siguiente, con sangría)
    ### Cambios
    - …

Sin dependencias: se lee una vez al arrancar (como VERSION).
"""
import re
from typing import Dict, List

VERSION_RE = re.compile(r"^##\s+(\d+\.\d+\.\d+)(?:\s+[—-]\s+(\d{4}-\d{2}-\d{2}))?\s*$")


def parse(text: str) -> List[Dict]:
    """[{version, date, sections: [{title, items: [str]}]}], en el orden del archivo."""
    versions: List[Dict] = []
    section = None
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        match = VERSION_RE.match(line)
        if match:
            versions.append({"version": match.group(1), "date": match.group(2), "sections": []})
            section = None
            continue
        if not versions:
            continue
        if line.startswith("### "):
            section = {"title": line[4:].strip(), "items": []}
            versions[-1]["sections"].append(section)
        elif line.startswith("- ") and section is not None:
            section["items"].append(line[2:].strip())
        elif line.startswith("  ") and line.strip() and section is not None and section["items"]:
            section["items"][-1] += " " + line.strip()
    # Una versión sin viñetas no tiene Novedades: no se enseña
    for v in versions:
        v["sections"] = [s for s in v["sections"] if s["items"]]
    return [v for v in versions if v["sections"]]


def load(path: str) -> List[Dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return parse(f.read())
    except OSError:
        return []
