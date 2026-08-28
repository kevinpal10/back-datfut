"""Endpoints del agente "Entrenador Táctico" (SPEC §5.3)."""

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from core.season import DEFAULT_SEASON
from services.agent_service import AgentService

router = APIRouter(prefix="/agent", tags=["Agent"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    player_id: Optional[int] = None
    season: int = DEFAULT_SEASON
    conversation_id: Optional[str] = None


class Ejercicio(BaseModel):
    nombre: str
    duracion_min: int
    descripcion: str


class Routine(BaseModel):
    posicion: str
    tiempo_minutos: int
    minutos_asignados: int
    ejercicios: list[Ejercicio]


class ChatResponse(BaseModel):
    conversation_id: str
    agent_response: str
    # Obligatorio cuando la respuesta menciona cifras: es el mecanismo que hace
    # auditable la regla de "sin alucinaciones" (SPEC §5.3).
    sources: list[dict]
    # Nullable a propósito: si el usuario sólo preguntó, no se fuerza una rutina.
    routine: Optional[Routine] = None
    routine_id: Optional[int] = None
    # `true` cuando no hay modelo disponible y la respuesta es determinista.
    degraded: bool = False


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    return AgentService.chat(
        message=payload.message,
        player_id=payload.player_id,
        season=payload.season,
        conversation_id=payload.conversation_id,
    )


@router.get("/routines")
def routines(player_id: Optional[int] = None, limit: int = Query(20, ge=1, le=100)):
    """Historial de rutinas generadas (SPEC §2.1.6)."""
    return AgentService.history(player_id, limit)


@router.get("/runs")
def runs(conversation_id: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    """Auditoría: herramientas invocadas, argumentos y latencia (SPEC §2.2.3)."""
    return AgentService.runs(conversation_id, limit)
