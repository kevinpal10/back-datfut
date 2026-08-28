"""La traducción de posición ocurre en un único punto del backend (SPEC §5.4)."""

import pytest

from core.positions import POSICIONES_ES, normalize_es, to_spanish


@pytest.mark.parametrize("ingles,espanol", [
    ("Goalkeeper", "portero"),
    ("Defender", "defensa"),
    ("Midfielder", "mediocampista"),
    ("Attacker", "delantero"),
    ("  attacker  ", "delantero"),
])
def test_traduce_las_cuatro_posiciones(ingles, espanol):
    assert to_spanish(ingles) == espanol


def test_posicion_desconocida_no_se_inventa():
    assert to_spanish("Sweeper") is None
    assert to_spanish(None) is None


def test_normalize_es_acepta_ambos_idiomas():
    assert normalize_es("Delantero") == "delantero"
    assert normalize_es("Attacker") == "delantero"
    assert normalize_es("banquillo") is None


def test_el_catalogo_cubre_todas_las_posiciones():
    from agent.tools import _CATALOG
    assert set(_CATALOG["ejercicios"]) == set(POSICIONES_ES)
    for ejercicios in _CATALOG["ejercicios"].values():
        assert ejercicios
        for ejercicio in ejercicios:
            assert ejercicio["duracion_min"] > 0
            assert ejercicio["descripcion"].strip()
