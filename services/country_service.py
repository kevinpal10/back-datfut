import math

import pandas as pd

from clients.errors import DatabaseError
from clients.football_api_client import ApiResult
from clients.football_api_client import football_client as client
from database.connection import engine, run_with_retry


def _jsonable(value):
    """Convierte un valor de pandas a algo que `json.dumps` acepte.

    `df.to_dict()` devuelve `NaN` para las celdas vacías y tipos de numpy para
    los números. Ninguno de los dos es JSON válido: `NaN`, `inf` y `-inf` hacen
    que Starlette falle con "Out of range float values are not JSON compliant"
    al renderizar la respuesta — es decir, **después** de que el servicio haya
    devuelto, así que ningún try/except de aquí lo atraparía.
    """
    if value is None or value is pd.NaT:
        return None
    # Tipos de numpy (int64, float64, bool_) → equivalente de Python.
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


class CountriesService:

    @staticmethod
    def get_countries() -> list[dict]:
        """Catálogo de países desde PostgreSQL (Neon), no desde api-football."""
        try:
            # Con reintento: en el plan gratuito Neon suspende la base y la
            # primera conexion tras un rato de inactividad falla mientras
            # despierta. Sin esto, la primera visita devolvia 503 y la pantalla
            # de paises salia vacia.
            df = run_with_retry(
                lambda: pd.read_sql("SELECT * FROM db_countries", engine)
            )
        except Exception as exc:
            # Antes devolvía `0`, y el frontend hacía `.filter()` sobre un número.
            # Fallar con un error tipado deja que `main.py` responda un 503 limpio.
            raise DatabaseError(f"No se pudo leer db_countries: {exc}") from exc

        return [
            {clave: _jsonable(valor) for clave, valor in fila.items()}
            for fila in df.to_dict(orient="records")
        ]

    @staticmethod
    def get_country_info(country_name: str) -> ApiResult:
        """Devuelve el *equipo* (selección nacional) cuyo nombre coincide."""
        return client.get("teams", params={"name": country_name})
