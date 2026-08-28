from clients.football_api_client import ApiResult
from clients.football_api_client import football_client as client


class TeamService:

    @staticmethod
    def get_teams_by_id(team_id: int) -> ApiResult:
        return client.get("teams", params={"id": team_id})

    @staticmethod
    def get_teams_by_country(country: str) -> ApiResult:
        return client.get("teams", params={"country": country})

    @staticmethod
    def get_teams_by_code(code: str) -> ApiResult:
        return client.get("teams", params={"code": code})

    @staticmethod
    def get_teams_by_league_and_season(league: str, season: int) -> ApiResult:
        return client.get("teams", params={"league": league, "season": season})
