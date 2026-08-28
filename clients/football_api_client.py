"""Cliente HTTP de api-football v3.

Es el único punto del backend que habla con la API externa, y concentra tres
responsabilidades que antes estaban repartidas o ausentes:

1. **Desenvolver** la respuesta: los servicios reciben ya el array `response`,
   no la envoltura. Antes cada servicio hacía `data["response"]` y reventaba con
   `KeyError` cuando la API devolvía un error.
2. **Detectar errores** de la API externa (cuota agotada, llave inválida, caída)
   y convertirlos en `ApiFootballError`.
3. **Cachear** 24 h, y servir la copia rancia cuando la API falla (SPEC §4.3).
"""

from typing import Any, NamedTuple, Optional

import requests

from clients.cache import TtlCache, build_key
from clients.errors import (
    AUTH_ERROR,
    QUOTA_EXCEEDED,
    UPSTREAM_ERROR,
    ApiFootballError,
)
from config import FOOTBALL_API_BASE_URL, FOOTBALL_API_KEY

# Sin timeout, una caída de la API externa retiene un worker del threadpool
# indefinidamente.
REQUEST_TIMEOUT_SECONDS = 15


class ApiResult(NamedTuple):
    """Datos más la marca de si vienen de una copia rancia de la caché."""

    data: Any
    stale: bool


def _classify(errors: Any) -> tuple[str, str]:
    """Traduce el campo `errors` de api-football a un `kind` de los nuestros.

    api-football devuelve `errors: []` cuando todo va bien y un diccionario
    (`{"requests": "..."}`, `{"token": "..."}`) cuando algo falla; el código de
    estado HTTP sigue siendo 200 en muchos de esos casos, así que inspeccionar
    el cuerpo no es opcional.
    """
    text = str(errors).lower()
    if "requests" in text or "limit" in text or "quota" in text:
        return QUOTA_EXCEEDED, f"Cuota de api-football agotada: {errors}"
    if "token" in text or "key" in text or "subscription" in text:
        return AUTH_ERROR, f"Credencial de api-football rechazada: {errors}"
    return UPSTREAM_ERROR, f"api-football devolvió un error: {errors}"


class FootballApiClient:

    def __init__(
        self,
        api_key: str,
        base_url: str = FOOTBALL_API_BASE_URL,
        cache: Optional[TtlCache] = None,
    ):
        self.base_url = base_url
        self.headers = {"x-apisports-key": api_key}
        self.cache = cache if cache is not None else TtlCache()

    # ── API pública ──────────────────────────────────────────────────────────

    def get(self, endpoint: str, params: Optional[dict] = None) -> ApiResult:
        """Devuelve el array `response` de api-football, con caché y respaldo.

        Lanza `ApiFootballError` sólo cuando la API falla **y** no hay ninguna
        copia previa que servir.
        """
        key = build_key(endpoint, params)

        hit, value = self.cache.get_fresh(key)
        if hit:
            return ApiResult(value, stale=False)

        try:
            response = self._fetch(endpoint, params)
        except ApiFootballError:
            # SPEC §4.3: antes de rendirse, servir lo último que se supo.
            hit, value = self.cache.get_any(key)
            if hit:
                return ApiResult(value, stale=True)
            raise

        self.cache.set(key, response)
        return ApiResult(response, stale=False)

    # ── Interno ──────────────────────────────────────────────────────────────

    def _fetch(self, endpoint: str, params: Optional[dict]) -> Any:
        url = f"{self.base_url}/{endpoint}"

        try:
            http_response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise ApiFootballError(
                UPSTREAM_ERROR, f"No se pudo contactar con api-football: {exc}"
            ) from exc

        if http_response.status_code == 429:
            raise ApiFootballError(
                QUOTA_EXCEEDED, "api-football respondió 429 (demasiadas peticiones)."
            )
        if http_response.status_code in (401, 403):
            raise ApiFootballError(
                AUTH_ERROR,
                f"api-football rechazó la credencial ({http_response.status_code}).",
            )
        if http_response.status_code >= 400:
            raise ApiFootballError(
                UPSTREAM_ERROR,
                f"api-football respondió {http_response.status_code}.",
            )

        try:
            payload = http_response.json()
        except ValueError as exc:
            raise ApiFootballError(
                UPSTREAM_ERROR, "api-football devolvió un cuerpo que no es JSON."
            ) from exc

        errors = payload.get("errors")
        # `errors` es `[]` cuando no hay error y un dict con mensajes cuando sí.
        if errors:
            kind, message = _classify(errors)
            raise ApiFootballError(kind, message)

        if "response" not in payload:
            raise ApiFootballError(
                UPSTREAM_ERROR, "api-football devolvió una respuesta sin campo 'response'."
            )

        return payload["response"]


# Instancia compartida por todos los servicios: la llave se lee una sola vez,
# desde variables de entorno, y la caché es común a todo el proceso.
football_client = FootballApiClient(FOOTBALL_API_KEY)
