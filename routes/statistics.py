"""Estadísticas de un jugador.

La ruta canónica es `/statistics/` (SPEC §5.2). `/statics/` era un typo heredado
del que dependía el frontend: se mantiene como alias para no romper clientes
antiguos, pero no debe usarse en código nuevo.
"""

from fastapi import APIRouter, Response

from core.http import serve
from core.season import DEFAULT_SEASON
from services.statistics_service import StatisticsService

router = APIRouter(prefix="/statistics", tags=["Statistics"])
legacy_router = APIRouter(prefix="/statics", tags=["Statistics (alias obsoleto)"])


def _get_player_stats(player_id: int, season: int, response: Response):
    return serve(StatisticsService.get_player_stats(player_id, season), response)


@router.get("/{player_id}")
def get_player_stats(player_id: int, response: Response, season: int = DEFAULT_SEASON):
    return _get_player_stats(player_id, season, response)


@legacy_router.get("/{player_id}", deprecated=True)
def get_player_stats_legacy(player_id: int, response: Response, season: int = DEFAULT_SEASON):
    return _get_player_stats(player_id, season, response)
