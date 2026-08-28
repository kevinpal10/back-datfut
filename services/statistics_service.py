from clients.football_api_client import ApiResult
from clients.football_api_client import football_client as client
from core.season import DEFAULT_SEASON


class StatisticsService:

    @staticmethod
    def get_player_stats(player_id: int, season: int = DEFAULT_SEASON) -> ApiResult:
        return client.get("players", params={"id": player_id, "season": season})
