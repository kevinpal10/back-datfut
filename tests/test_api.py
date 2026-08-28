"""Pruebas de los endpoints, sin tocar api-football ni PostgreSQL."""

import pytest
from fastapi.testclient import TestClient

import main
from clients.errors import QUOTA_EXCEEDED, ApiFootballError
from clients.football_api_client import ApiResult


@pytest.fixture
def client(monkeypatch):
    # `lifespan` intentaría crear el esquema en Neon: se anula.
    monkeypatch.setattr("main.agent_store.ensure_schema", lambda: True)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def sin_base_de_datos(monkeypatch):
    """El agente persiste "a mejor esfuerzo"; en pruebas se corta el acceso."""
    monkeypatch.setattr("database.agent_store.save_routine", lambda *a, **k: 1)
    monkeypatch.setattr("database.agent_store.log_run", lambda *a, **k: None)


def test_health_expone_cache_y_modo_del_agente(client):
    cuerpo = client.get("/health").json()
    assert cuerpo["status"] == "ok"
    assert "entries" in cuerpo["cache"]
    assert cuerpo["agent"]["modo"] in ("modelo", "degradado")


def test_busqueda_corta_se_rechaza(client):
    respuesta = client.get("/players/search", params={"q": "ha"})
    assert respuesta.status_code == 422


def test_cuota_agotada_devuelve_503_tipado(client, monkeypatch):
    def falla(*args, **kwargs):
        raise ApiFootballError(QUOTA_EXCEEDED, "cuota agotada")

    monkeypatch.setattr("services.leagues_service.client.get", falla)
    respuesta = client.get("/leagues/Spain")
    assert respuesta.status_code == 503
    assert respuesta.json()["detail"] == QUOTA_EXCEEDED
    assert respuesta.json()["cached"] is False


def test_datos_rancios_se_sirven_con_cabecera(client, monkeypatch):
    monkeypatch.setattr(
        "services.leagues_service.client.get",
        lambda *a, **k: ApiResult([{"league": {"id": 1}}], stale=True),
    )
    respuesta = client.get("/leagues/Spain")
    assert respuesta.status_code == 200
    assert respuesta.headers["X-Data-Stale"] == "true"
    assert respuesta.json() == [{"league": {"id": 1}}]


def test_datos_frescos_no_llevan_cabecera(client, monkeypatch):
    monkeypatch.setattr(
        "services.leagues_service.client.get",
        lambda *a, **k: ApiResult([], stale=False),
    )
    respuesta = client.get("/leagues/Spain")
    assert "X-Data-Stale" not in respuesta.headers


def test_alias_statics_sigue_funcionando(client, monkeypatch):
    monkeypatch.setattr(
        "services.statistics_service.client.get",
        lambda *a, **k: ApiResult([{"player": {"id": 184}}], stale=False),
    )
    for ruta in ("/statistics/184", "/statics/184"):
        respuesta = client.get(ruta, params={"season": 2024})
        assert respuesta.status_code == 200, ruta
        assert respuesta.json()[0]["player"]["id"] == 184


def test_chat_degradado_responde_con_rutina_acotada(client, monkeypatch):
    # Sin credenciales de AWS el agente degrada, pero sigue devolviendo cifras
    # reales y una rutina que respeta el tiempo pedido.
    monkeypatch.setattr("agent.react_agent.bedrock_is_configured", lambda: False)
    monkeypatch.setattr(
        "services.statistics_service.client.get",
        lambda *a, **k: ApiResult(
            [{
                "player": {"id": 184, "name": "E. Haaland", "age": 24},
                "statistics": [{
                    "league": {"name": "Premier League"},
                    "team": {"name": "Manchester City"},
                    "games": {"appearences": 31, "minutes": 2650,
                              "position": "Attacker", "rating": "7.4"},
                    "goals": {"total": 27, "assists": 3},
                    "shots": {"total": 95, "on": 48},
                    "passes": {"accuracy": 74, "key": 22},
                    "duels": {"won": 120, "total": 300},
                    "dribbles": {"success": 20, "attempts": 40},
                }],
            }],
            stale=False,
        ),
    )

    respuesta = client.post("/agent/chat", json={
        "message": "Quiero mejorar mi definición, tengo 20 minutos.",
        "player_id": 184,
        "season": 2024,
    })
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()

    assert cuerpo["degraded"] is True
    assert cuerpo["conversation_id"]
    # `sources` es obligatorio cuando se citan cifras (SPEC §5.3).
    assert any(s["tool"] == "obtener_metricas_jugador" for s in cuerpo["sources"])

    rutina = cuerpo["routine"]
    assert rutina["posicion"] == "delantero"      # traducido desde "Attacker"
    assert sum(e["duracion_min"] for e in rutina["ejercicios"]) <= 20


def test_chat_sin_datos_no_inventa_cifras(client, monkeypatch):
    monkeypatch.setattr("agent.react_agent.bedrock_is_configured", lambda: False)
    monkeypatch.setattr(
        "services.statistics_service.client.get",
        lambda *a, **k: ApiResult([], stale=False),
    )

    cuerpo = client.post("/agent/chat", json={
        "message": "Dame una rutina de 15 minutos.",
        "player_id": 999999,
        "season": 2024,
    }).json()

    assert "no logré recuperar" in cuerpo["agent_response"].lower()
    assert sum(e["duracion_min"] for e in cuerpo["routine"]["ejercicios"]) <= 15


def test_countries_convierte_nan_a_null(client, monkeypatch):
    """`db_countries` trae celdas vacías; NaN no es JSON válido y reventaba
    al renderizar la respuesta, fuera del alcance de cualquier try/except."""
    import numpy as np
    import pandas as pd

    marco = pd.DataFrame([
        {"id": 1, "name": "Ecuador", "code": "ECU", "founded": 1925.0},
        {"id": 2, "name": "Argentina", "code": None, "founded": np.nan},
    ])
    monkeypatch.setattr("services.country_service.pd.read_sql", lambda *a, **k: marco)

    respuesta = client.get("/countries/")
    assert respuesta.status_code == 200

    filas = respuesta.json()
    assert filas[0]["founded"] == 1925
    assert filas[1]["founded"] is None
    assert filas[1]["code"] is None
