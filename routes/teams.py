from fastapi import APIRouter, Response

from core.http import serve
from services.team_service import TeamService

router = APIRouter(prefix="/teams", tags=["Teams"])


@router.get("/id/{team_id}")
def get_team_by_id(team_id: int, response: Response):
    return serve(TeamService.get_teams_by_id(team_id), response)


@router.get("/country/{country}")
def get_teams_by_country(country: str, response: Response):
    return serve(TeamService.get_teams_by_country(country), response)


@router.get("/code/{code}")
def get_teams_by_code(code: str, response: Response):
    return serve(TeamService.get_teams_by_code(code), response)


@router.get("/league/{league}/season/{season}")
def get_teams_by_league_and_season(league: str, season: int, response: Response):
    return serve(TeamService.get_teams_by_league_and_season(league, season), response)
