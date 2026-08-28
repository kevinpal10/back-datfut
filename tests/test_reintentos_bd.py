"""El reintento contra la base de datos dormida (Neon plan gratuito).

En el plan gratuito Neon suspende la base tras un rato de inactividad. La
primera conexión mientras despierta falla, y eso devolvía un 503 que dejaba la
pantalla de países vacía. `pool_pre_ping` no lo cubre: sirve para una conexión
rancia del pool, no para abrir una nueva contra un endpoint suspendido.
"""

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from database import connection as conexion
from database.connection import run_with_retry


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Las pruebas no deben dormir de verdad."""
    dormido = []
    monkeypatch.setattr(conexion.time, "sleep", lambda s: dormido.append(s))
    return dormido


def _operational_error(mensaje="SSL connection has been closed unexpectedly"):
    return OperationalError(mensaje, None, Exception(mensaje))


def test_devuelve_el_valor_si_va_a_la_primera():
    assert run_with_retry(lambda: "ok") == "ok"


def test_no_reintenta_cuando_no_hace_falta(sin_esperas):
    llamadas = []
    run_with_retry(lambda: llamadas.append(1))
    assert len(llamadas) == 1
    assert sin_esperas == []


def test_reintenta_y_acaba_funcionando_cuando_la_base_despierta(sin_esperas):
    intentos = []

    def operacion():
        intentos.append(1)
        if len(intentos) < 3:
            raise _operational_error()
        return "despierta"

    assert run_with_retry(operacion) == "despierta"
    assert len(intentos) == 3


def test_la_espera_crece_entre_intentos(sin_esperas):
    def siempre_falla():
        raise _operational_error()

    with pytest.raises(OperationalError):
        run_with_retry(siempre_falla)

    # Dos esperas para tres intentos, y la segunda mayor que la primera.
    assert len(sin_esperas) == conexion.REINTENTOS - 1
    assert sin_esperas[1] > sin_esperas[0]


def test_se_rinde_tras_el_ultimo_intento(sin_esperas):
    intentos = []

    def siempre_falla():
        intentos.append(1)
        raise _operational_error()

    with pytest.raises(OperationalError):
        run_with_retry(siempre_falla)
    assert len(intentos) == conexion.REINTENTOS


def test_un_error_de_sql_no_se_reintenta(sin_esperas):
    """Reintentar un fallo real esconde el problema en vez de resolverlo."""
    intentos = []

    def sql_malo():
        intentos.append(1)
        raise ValueError('relation "no_existe" does not exist')

    with pytest.raises(ValueError):
        run_with_retry(sql_malo)

    assert len(intentos) == 1
    assert sin_esperas == []


def test_dbapi_error_sin_conexion_invalidada_no_se_reintenta(sin_esperas):
    intentos = []

    def fallo():
        intentos.append(1)
        exc = DBAPIError("stmt", None, Exception("boom"))
        exc.connection_invalidated = False
        raise exc

    with pytest.raises(DBAPIError):
        run_with_retry(fallo)

    assert len(intentos) == 1


def test_el_engine_esta_configurado_para_neon():
    """Las tres opciones que evitan el 503; si alguien las quita, salta aquí."""
    assert conexion.engine.pool._pre_ping is True
    assert conexion.engine.pool._recycle == 300
