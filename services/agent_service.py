"""Orquestación del agente: ejecutar, persistir y auditar."""

import logging
from typing import Optional

from agent.react_agent import AgentUnavailable, run_con_modelo, run_sin_modelo
from core.season import DEFAULT_SEASON
from database import agent_store

logger = logging.getLogger(__name__)


class AgentService:

    @staticmethod
    def chat(
        message: str,
        player_id: Optional[int] = None,
        season: int = DEFAULT_SEASON,
        conversation_id: Optional[str] = None,
    ) -> dict:
        conversation_id = conversation_id or agent_store.new_conversation_id()

        try:
            resultado = run_con_modelo(message, player_id, season)
        except AgentUnavailable as exc:
            # Sin modelo el flujo sigue vivo con cifras reales y rutina del
            # catálogo; SPEC §3, Módulo 3 exige degradar, no fallar.
            logger.info("Agente degradado: %s", exc)
            resultado = run_sin_modelo(message, player_id, season, str(exc))

        routine = resultado.get("routine")
        routine_id = None
        if routine:
            routine_id = agent_store.save_routine(routine, player_id, season)

        agent_store.log_run(
            conversation_id=conversation_id,
            prompt=message,
            tool_calls=resultado.get("tool_calls", []),
            latency_ms=resultado.get("latency_ms"),
            model=resultado.get("model"),
        )

        return {
            "conversation_id": conversation_id,
            "agent_response": resultado["agent_response"],
            "sources": resultado["sources"],
            "routine": routine,
            "routine_id": routine_id,
            "degraded": resultado["degradado"],
        }

    @staticmethod
    def history(player_id: Optional[int] = None, limit: int = 20) -> list[dict]:
        return agent_store.list_routines(player_id, limit)

    @staticmethod
    def runs(conversation_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        return agent_store.list_runs(conversation_id, limit)
