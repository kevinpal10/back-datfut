"""Traducción de posiciones inglés → español.

SPEC §5.4: api-football entrega la posición en inglés (`Goalkeeper`, `Defender`,
`Midfielder`, `Attacker`) y las herramientas del agente la esperan en español.
La conversión ocurre **en un único punto del backend**, nunca en el modelo: si
el modelo tuviera que traducirla, una alucinación en la traducción cambiaría la
rutina entera.
"""

POSICIONES_ES = ("portero", "defensa", "mediocampista", "delantero")

_EN_TO_ES = {
    "goalkeeper": "portero",
    "defender": "defensa",
    "midfielder": "mediocampista",
    "attacker": "delantero",
}


def to_spanish(position: str | None) -> str | None:
    """`'Attacker'` → `'delantero'`. Devuelve `None` si no se reconoce."""
    if not position:
        return None
    return _EN_TO_ES.get(position.strip().lower())


def normalize_es(posicion: str | None) -> str | None:
    """Normaliza una posición que ya viene en español (o en inglés por error)."""
    if not posicion:
        return None
    value = posicion.strip().lower()
    if value in POSICIONES_ES:
        return value
    return _EN_TO_ES.get(value)
