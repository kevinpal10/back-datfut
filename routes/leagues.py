from fastapi import APIRouter, Response

from core.http import serve
from services.leagues_service import LeaguesService

router = APIRouter(prefix="/leagues", tags=["Leagues"])


@router.get("/teams/{league_id}/{season}")
def get_teams_by_league(league_id: int, season: int, response: Response):
    return serve(LeaguesService.get_teams_by_league(league_id, season), response)


# Va después de `/teams/...` a propósito: si se declarara antes, `/leagues/teams`
# entraría por aquí tomando "teams" como nombre de país.
@router.get("/{country_name}")
def get_leagues(country_name: str, response: Response):
    return serve(LeaguesService.get_leagues_by_country(country_name), response)
