"""Utilidades compartidas por los routers."""

from fastapi import Response

from clients.football_api_client import ApiResult

# Cabecera con la que el backend avisa de que los datos salen de una copia
# rancia de la caché porque api-football falló (SPEC §4.3). El cuerpo no cambia,
# así que el frontend sigue funcionando aunque no la lea.
STALE_HEADER = "X-Data-Stale"


def serve(result: ApiResult, response: Response):
    """Devuelve los datos del `ApiResult` y marca la respuesta si son rancios."""
    if result.stale:
        response.headers[STALE_HEADER] = "true"
    return result.data
