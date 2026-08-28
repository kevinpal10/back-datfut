from clients.football_api_client import ApiResult
from clients.football_api_client import football_client as client


class LeaguesService:

    @staticmethod
    def get_leagues_by_country(country: str) -> ApiResult:
        return client.get("leagues", params={"country": country})

    @staticmethod
    def get_teams_by_league(league_id: int, season: int) -> ApiResult:
        return client.get("teams", params={"league": league_id, "season": season})
