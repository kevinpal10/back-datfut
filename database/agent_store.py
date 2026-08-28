"""Persistencia del agente: rutinas generadas y auditoría de ejecuciones.

Esquema de SPEC §5.5. `agent_runs` es lo que hace posible auditar al agente
(caso de uso 2.2.3): qué herramientas invocó, con qué argumentos y con qué
latencia.

Un fallo al guardar **no** tumba la conversación: el usuario ya tiene su
respuesta y perder una fila de auditoría es preferible a devolverle un 500.
"""

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import text

from database.connection import engine

logger = logging.getLogger(__name__)

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS routines (
        id          BIGSERIAL PRIMARY KEY,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        player_id   INTEGER,
        season      INTEGER,
        posicion    TEXT NOT NULL,
        minutos     INTEGER NOT NULL,
        payload     JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id              BIGSERIAL PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        prompt          TEXT NOT NULL,
        tool_calls      JSONB NOT NULL,
        latency_ms      INTEGER,
        model           TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS agent_runs_conversation_idx ON agent_runs (conversation_id)",
    "CREATE INDEX IF NOT EXISTS routines_player_idx ON routines (player_id, season)",
)


def ensure_schema() -> bool:
    """Crea las tablas si no existen. Devuelve `False` si la BD no responde."""
    try:
        with engine.begin() as connection:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(text(statement))
        return True
    except Exception as exc:
        logger.warning("No se pudo preparar el esquema del agente: %s", exc)
        return False


def new_conversation_id() -> str:
    return f"c-{uuid.uuid4().hex[:8]}"


def save_routine(
    routine: dict, player_id: Optional[int], season: Optional[int]
) -> Optional[int]:
    """Guarda una rutina en el historial. Devuelve su id, o `None` si falló."""
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO routines (player_id, season, posicion, minutos, payload)
                    VALUES (:player_id, :season, :posicion, :minutos, CAST(:payload AS JSONB))
                    RETURNING id
                    """
                ),
                {
                    "player_id": player_id,
                    "season": season,
                    "posicion": routine.get("posicion"),
                    "minutos": routine.get("tiempo_minutos"),
                    "payload": json.dumps(routine, ensure_ascii=False),
                },
            ).first()
            return row[0] if row else None
    except Exception as exc:
        logger.warning("No se pudo guardar la rutina: %s", exc)
        return None


def log_run(
    conversation_id: str,
    prompt: str,
    tool_calls: list,
    latency_ms: Optional[int],
    model: Optional[str],
) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO agent_runs (conversation_id, prompt, tool_calls, latency_ms, model)
                    VALUES (:conversation_id, :prompt, CAST(:tool_calls AS JSONB), :latency_ms, :model)
                    """
                ),
                {
                    "conversation_id": conversation_id,
                    "prompt": prompt,
                    "tool_calls": json.dumps(tool_calls, ensure_ascii=False, default=str),
                    "latency_ms": latency_ms,
                    "model": model,
                },
            )
    except Exception as exc:
        logger.warning("No se pudo registrar la ejecución del agente: %s", exc)


def list_routines(player_id: Optional[int] = None, limit: int = 20) -> list[dict]:
    """Historial de rutinas, la más reciente primero (SPEC §2.1.6)."""
    query = """
        SELECT id, created_at, player_id, season, posicion, minutos, payload
        FROM routines
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """.format(where="WHERE player_id = :player_id" if player_id else "")

    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(query),
                {"limit": limit, **({"player_id": player_id} if player_id else {})},
            ).mappings()
            return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("No se pudo leer el historial de rutinas: %s", exc)
        return []


def list_runs(conversation_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Auditoría de ejecuciones del agente (SPEC §2.2.3)."""
    query = """
        SELECT id, conversation_id, created_at, prompt, tool_calls, latency_ms, model
        FROM agent_runs
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """.format(where="WHERE conversation_id = :conversation_id" if conversation_id else "")

    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(query),
                {
                    "limit": limit,
                    **({"conversation_id": conversation_id} if conversation_id else {}),
                },
            ).mappings()
            return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("No se pudo leer la auditoría del agente: %s", exc)
        return []
