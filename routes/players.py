from fastapi import APIRouter, HTTPException, Query, Response

from core.http import serve
from services.player_service import MIN_SEARCH_LENGTH, PlayerService

router = APIRouter(prefix="/players", tags=["Players"])


# Declarada antes que `/{id_team}`: si no, FastAPI intentaría interpretar
# "search" como un entero y respondería 422.
@router.get("/search")
def search_players(response: Response, q: str = Query(..., description="Nombre o parte del nombre")):
    query = q.strip()
    if len(query) < MIN_SEARCH_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"La búsqueda debe tener al menos {MIN_SEARCH_LENGTH} caracteres.",
        )
    return serve(PlayerService.search_players(query), response)


@router.get("/{id_team}")
def get_players_by_team(id_team: int, response: Response):
    return serve(PlayerService.get_players_by_team(id_team), response)
