"""Caché de 24 h, detección de errores y respaldo rancio (SPEC §4.3 y §6)."""

import pytest

from clients.cache import TtlCache, build_key
from clients.errors import AUTH_ERROR, QUOTA_EXCEEDED, ApiFootballError
from clients.football_api_client import FootballApiClient


class RespuestaFalsa:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def cliente_con(respuestas, monkeypatch):
    """Cliente cuyo `requests.get` devuelve las respuestas dadas, en orden."""
    client = FootballApiClient("k", "https://api.test", cache=TtlCache())
    pendientes = list(respuestas)

    def fake_get(url, headers=None, params=None, timeout=None):
        siguiente = pendientes.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    monkeypatch.setattr("clients.football_api_client.requests.get", fake_get)
    return client, pendientes


def test_desenvuelve_response_y_cachea(monkeypatch):
    client, pendientes = cliente_con(
        [RespuestaFalsa({"errors": [], "response": [{"id": 1}]})], monkeypatch
    )
    primero = client.get("teams", {"id": 1})
    assert primero.data == [{"id": 1}]
    assert primero.stale is False

    # La segunda llamada sale de la caché: no quedan respuestas que consumir.
    segundo = client.get("teams", {"id": 1})
    assert segundo.data == [{"id": 1}]
    assert pendientes == []


def test_cuota_agotada_se_detecta_en_el_cuerpo(monkeypatch):
    # api-football responde 200 con `errors` poblado: mirar sólo el status no basta.
    client, _ = cliente_con(
        [RespuestaFalsa({"errors": {"requests": "You have reached the request limit"}})],
        monkeypatch,
    )
    with pytest.raises(ApiFootballError) as exc:
        client.get("teams", {"id": 1})
    assert exc.value.kind == QUOTA_EXCEEDED


def test_llave_invalida_se_clasifica_como_auth(monkeypatch):
    client, _ = cliente_con(
        [RespuestaFalsa({"errors": {"token": "invalid api key"}})], monkeypatch
    )
    with pytest.raises(ApiFootballError) as exc:
        client.get("teams", {"id": 2})
    assert exc.value.kind == AUTH_ERROR


def test_sirve_copia_rancia_cuando_la_api_falla(monkeypatch):
    client, _ = cliente_con(
        [
            RespuestaFalsa({"errors": [], "response": [{"id": 7}]}),
            RespuestaFalsa({"errors": {"requests": "limit"}}),
        ],
        monkeypatch,
    )
    client.get("teams", {"id": 7})
    client.cache.ttl_seconds = -1  # fuerza el vencimiento del TTL

    respaldo = client.get("teams", {"id": 7})
    assert respaldo.data == [{"id": 7}]
    assert respaldo.stale is True


def test_sin_copia_previa_el_error_se_propaga(monkeypatch):
    client, _ = cliente_con([RespuestaFalsa({}, status_code=429)], monkeypatch)
    with pytest.raises(ApiFootballError) as exc:
        client.get("teams", {"id": 99})
    assert exc.value.kind == QUOTA_EXCEEDED


def test_la_clave_de_cache_no_depende_del_orden_de_los_parametros():
    assert build_key("teams", {"a": 1, "b": 2}) == build_key("teams", {"b": 2, "a": 1})
    assert build_key("teams", {"a": 1}) != build_key("teams", {"a": 2})


def test_la_entrada_vencida_no_se_sirve_como_fresca():
    cache = TtlCache(ttl_seconds=-1)
    cache.set("k", "v")
    assert cache.get_fresh("k") == (False, None)
    assert cache.get_any("k") == (True, "v")
