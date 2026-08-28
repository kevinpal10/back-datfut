from clients.football_api_client import ApiResult
from clients.football_api_client import football_client as client

# api-football rechaza búsquedas más cortas en `players/profiles`.
MIN_SEARCH_LENGTH = 3


class PlayerService:

    @staticmethod
    def get_players_by_team(team_id: int) -> ApiResult:
        return client.get("players/squads", params={"team": team_id})

    @staticmethod
    def search_players(query: str) -> ApiResult:
        """Busca jugadores por nombre (SPEC §2.1.1: llegar a la ficha sin
        recorrer país → liga → equipo).

        Aplana la envoltura `{"player": {...}}` de `players/profiles` a la forma
        que consume el frontend, para que la pantalla de búsqueda no tenga que
        conocer el formato de api-football.
        """
        result = client.get("players/profiles", params={"search": query})
        players = [
            {
                "player_id": item["player"]["id"],
                "name": item["player"]["name"],
                "firstname": item["player"].get("firstname"),
                "lastname": item["player"].get("lastname"),
                "age": item["player"].get("age"),
                "nationality": item["player"].get("nationality"),
                "position": item["player"].get("position"),
                "photo": item["player"].get("photo"),
            }
            for item in (result.data or [])
            if isinstance(item, dict) and isinstance(item.get("player"), dict)
        ]
        return ApiResult(players, result.stale)
