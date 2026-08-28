"""Herramientas expuestas al agente "Entrenador Táctico" (SPEC §5.4).

Dos reglas gobiernan este módulo:

* **El agente no genera números.** `obtener_metricas_jugador` devuelve un resumen
  plano calculado aquí a partir de api-football; el modelo sólo lo interpreta.
* **El límite de tiempo es una garantía del código, no una instrucción.**
  `sugerir_entrenamiento` recorta el catálogo hasta encajar en los minutos
  pedidos, así que el modelo no puede excederlo aunque lo intente.
"""

import json
from pathlib import Path
from typing import Any, Optional

from clients.errors import ApiFootballError
from core.positions import POSICIONES_ES, normalize_es, to_spanish
from core.season import DEFAULT_SEASON
from services.statistics_service import StatisticsService

# Límites del tiempo de entrenamiento admitido, en minutos.
MIN_MINUTOS = 5
MAX_MINUTOS = 120

_CATALOG_PATH = Path(__file__).resolve().parent / "exercises.json"


def _load_catalog() -> dict:
    with _CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


_CATALOG = _load_catalog()


# ── Esquemas que ve el modelo ────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "obtener_metricas_jugador",
        "description": (
            "Consulta las estadísticas reales de un jugador en una temporada. "
            "Devuelve goles, asistencias, tiros, precisión de pase, duelos y "
            "posición, desglosados por competición. Úsala SIEMPRE antes de "
            "emitir cualquier juicio técnico o mencionar una cifra."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_id": {
                    "type": "integer",
                    "description": "ID del jugador en api-football.",
                },
                "season": {
                    "type": "integer",
                    "description": "Año de la temporada (ej: 2024).",
                },
            },
            "required": ["player_id", "season"],
            "additionalProperties": False,
        },
    },
    {
        "name": "sugerir_entrenamiento",
        "description": (
            "Devuelve ejercicios pre-diseñados por posición y tiempo disponible. "
            "El catálogo es fijo: no inventes ejercicios ni modifiques las "
            "duraciones que devuelve esta herramienta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "posicion": {
                    "type": "string",
                    "enum": list(POSICIONES_ES),
                    "description": "Posición del jugador, en español.",
                },
                "minutos_disponibles": {
                    "type": "integer",
                    "description": f"Minutos totales disponibles ({MIN_MINUTOS}–{MAX_MINUTOS}).",
                },
            },
            "required": ["posicion", "minutos_disponibles"],
            "additionalProperties": False,
        },
    },
]


# ── Implementaciones ─────────────────────────────────────────────────────────


def _pct(part: Optional[float], total: Optional[float]) -> Optional[float]:
    if not part or not total:
        return None
    return round(part / total * 100, 1)


def _resumen_competicion(stat: dict) -> dict:
    """Aplana una entrada de `statistics[]` a las cifras que importan."""
    games = stat.get("games") or {}
    goals = stat.get("goals") or {}
    shots = stat.get("shots") or {}
    passes = stat.get("passes") or {}
    duels = stat.get("duels") or {}
    dribbles = stat.get("dribbles") or {}

    return {
        "competicion": (stat.get("league") or {}).get("name"),
        "equipo": (stat.get("team") or {}).get("name"),
        "posicion": to_spanish(games.get("position")),
        "partidos": games.get("appearences"),
        "minutos": games.get("minutes"),
        "rating": games.get("rating"),
        "goles": goals.get("total"),
        "asistencias": goals.get("assists"),
        "tiros_totales": shots.get("total"),
        "tiros_a_puerta": shots.get("on"),
        "precision_tiro_pct": _pct(shots.get("on"), shots.get("total")),
        "pases_precision_pct": passes.get("accuracy"),
        "pases_clave": passes.get("key"),
        "duelos_ganados": duels.get("won"),
        "duelos_totales": duels.get("total"),
        "duelos_ganados_pct": _pct(duels.get("won"), duels.get("total")),
        "regates_completados": dribbles.get("success"),
        "regates_intentados": dribbles.get("attempts"),
    }


def obtener_metricas_jugador(player_id: int, season: int = DEFAULT_SEASON) -> dict:
    """Resumen plano por competición, no la envoltura cruda de api-football."""
    try:
        result = StatisticsService.get_player_stats(player_id, season)
    except ApiFootballError as exc:
        # El agente debe poder decir "no recuperé los datos" en lugar de
        # inventarlos: el fallo viaja como dato, no como excepción.
        return {
            "encontrado": False,
            "motivo": exc.kind,
            "mensaje": "No se pudieron recuperar las estadísticas de este jugador.",
        }

    entries = result.data or []
    if not entries:
        return {
            "encontrado": False,
            "motivo": "sin_datos",
            "mensaje": (
                f"api-football no tiene estadísticas del jugador {player_id} "
                f"en la temporada {season}."
            ),
        }

    entry = entries[0]
    player = entry.get("player") or {}
    competiciones = [_resumen_competicion(s) for s in (entry.get("statistics") or [])]

    # La posición del jugador es la de su primera competición registrada.
    posicion = next((c["posicion"] for c in competiciones if c["posicion"]), None)

    return {
        "encontrado": True,
        "desde_cache_rancia": result.stale,
        "player_id": player.get("id", player_id),
        "nombre": player.get("name"),
        "edad": player.get("age"),
        "nacionalidad": player.get("nationality"),
        "posicion": posicion,
        "temporada": season,
        "competiciones": competiciones,
    }


def sugerir_entrenamiento(posicion: str, minutos_disponibles: int) -> dict:
    """Selecciona ejercicios del catálogo sin exceder nunca los minutos pedidos.

    Recorre el catálogo por prioridad y salta el ejercicio que no quepa en el
    tiempo restante, en lugar de detenerse: así 20 minutos se llenan con dos
    bloques de 10 aunque el siguiente por prioridad fuera de 15.
    """
    normalizada = normalize_es(posicion)
    if normalizada is None:
        return {
            "ok": False,
            "motivo": "posicion_invalida",
            "mensaje": f"Posición no reconocida: {posicion!r}. Válidas: {', '.join(POSICIONES_ES)}.",
        }

    try:
        minutos = int(minutos_disponibles)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "motivo": "minutos_invalidos",
            "mensaje": f"`minutos_disponibles` debe ser un entero, llegó {minutos_disponibles!r}.",
        }

    if minutos < MIN_MINUTOS:
        return {
            "ok": False,
            "motivo": "minutos_invalidos",
            "mensaje": f"El tiempo mínimo de entrenamiento es {MIN_MINUTOS} minutos.",
        }
    minutos = min(minutos, MAX_MINUTOS)

    catalogo = sorted(
        _CATALOG["ejercicios"][normalizada], key=lambda e: e["prioridad"]
    )

    seleccionados: list[dict] = []
    restante = minutos
    for ejercicio in catalogo:
        if ejercicio["duracion_min"] <= restante:
            seleccionados.append(
                {
                    "nombre": ejercicio["nombre"],
                    "duracion_min": ejercicio["duracion_min"],
                    "descripcion": ejercicio["descripcion"],
                }
            )
            restante -= ejercicio["duracion_min"]

    return {
        "ok": True,
        "posicion": normalizada,
        "tiempo_minutos": minutos,
        "minutos_asignados": minutos - restante,
        "minutos_sin_asignar": restante,
        "catalogo_version": _CATALOG["version"],
        "ejercicios": seleccionados,
    }


# Despacho por nombre: lo usa el bucle ReAct al recibir un `tool_use`.
TOOL_IMPLEMENTATIONS = {
    "obtener_metricas_jugador": obtener_metricas_jugador,
    "sugerir_entrenamiento": sugerir_entrenamiento,
}


def execute_tool(name: str, arguments: dict) -> Any:
    """Ejecuta una herramienta por nombre, sin dejar escapar excepciones."""
    implementation = TOOL_IMPLEMENTATIONS.get(name)
    if implementation is None:
        return {"ok": False, "motivo": "herramienta_desconocida", "mensaje": name}
    try:
        return implementation(**arguments)
    except TypeError as exc:
        return {"ok": False, "motivo": "argumentos_invalidos", "mensaje": str(exc)}
