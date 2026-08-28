"""El límite de tiempo es una garantía del código (SPEC §5.3 y §6)."""

import pytest

from agent.react_agent import _validar_rutina, extraer_minutos
from agent.tools import MAX_MINUTOS, MIN_MINUTOS, sugerir_entrenamiento
from core.positions import POSICIONES_ES


@pytest.mark.parametrize("posicion", POSICIONES_ES)
@pytest.mark.parametrize("minutos", [5, 10, 15, 20, 30, 45, 60, 90, 120])
def test_la_rutina_nunca_excede_los_minutos_pedidos(posicion, minutos):
    rutina = sugerir_entrenamiento(posicion, minutos)
    assert rutina["ok"] is True
    total = sum(e["duracion_min"] for e in rutina["ejercicios"])
    assert total <= minutos
    assert total == rutina["minutos_asignados"]


def test_recorta_saltando_el_ejercicio_que_no_cabe():
    # Delantero: 5, 10, 10, 10, 15 por prioridad. Con 25 min debe encajar
    # 5+10+10 y saltarse el de 15, en vez de detenerse en el primero que no cabe.
    rutina = sugerir_entrenamiento("delantero", 25)
    duraciones = [e["duracion_min"] for e in rutina["ejercicios"]]
    assert sum(duraciones) == 25
    assert 15 not in duraciones


def test_el_minimo_se_respeta_con_un_solo_ejercicio():
    rutina = sugerir_entrenamiento("portero", MIN_MINUTOS)
    assert len(rutina["ejercicios"]) == 1
    assert rutina["ejercicios"][0]["duracion_min"] == MIN_MINUTOS


def test_rechaza_posicion_desconocida():
    rutina = sugerir_entrenamiento("lateral volante", 30)
    assert rutina["ok"] is False
    assert rutina["motivo"] == "posicion_invalida"


def test_rechaza_menos_del_minimo():
    rutina = sugerir_entrenamiento("defensa", 2)
    assert rutina["ok"] is False
    assert rutina["motivo"] == "minutos_invalidos"


def test_recorta_al_maximo_en_lugar_de_fallar():
    rutina = sugerir_entrenamiento("mediocampista", 500)
    assert rutina["ok"] is True
    assert rutina["tiempo_minutos"] == MAX_MINUTOS


def test_acepta_la_posicion_en_ingles_de_api_football():
    rutina = sugerir_entrenamiento("Attacker", 20)
    assert rutina["ok"] is True
    assert rutina["posicion"] == "delantero"


def test_validar_rutina_es_la_segunda_cerradura():
    # Una rutina construida por otra vía que excediera el tiempo se recorta.
    rutina = _validar_rutina({
        "posicion": "delantero",
        "tiempo_minutos": 20,
        "ejercicios": [
            {"nombre": "a", "duracion_min": 15, "descripcion": ""},
            {"nombre": "b", "duracion_min": 15, "descripcion": ""},
        ],
    })
    assert sum(e["duracion_min"] for e in rutina["ejercicios"]) <= 20
    assert rutina["minutos_asignados"] == 15


@pytest.mark.parametrize("mensaje,esperado", [
    ("Tengo 30 minutos libres", 30),
    ("dispongo de 45min", 45),
    ("quiero entrenar 1000 minutos", MAX_MINUTOS),
    ("no tengo tiempo", None),
    ("tengo 2 minutos", None),
])
def test_extraer_minutos_del_mensaje(mensaje, esperado):
    assert extraer_minutos(mensaje) == esperado
