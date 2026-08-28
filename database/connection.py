import logging
import time
from typing import Callable, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, OperationalError

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Neon es Postgres serverless: corta las conexiones ociosas y, en el plan
# gratuito, **suspende la base entera** tras un rato sin uso.
#
#   pool_pre_ping → comprueba la conexión con un SELECT 1 antes de entregarla y
#                   la reabre si está muerta. Cubre la conexión rancia del pool.
#   pool_recycle  → la descarta antes de que Neon la cierre por inactividad.
#   connect_timeout → no dejar una petición colgada esperando a un endpoint
#                   suspendido; mejor fallar rápido y reintentar (ver abajo).
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": 10},
)

T = TypeVar("T")

# Cuántas veces reintentar y cuánto esperar entre intentos. Neon tarda del orden
# de 1-3 s en despertar, así que 3 intentos con espera creciente bastan.
REINTENTOS = 3
ESPERA_INICIAL_S = 1.0


def run_with_retry(operacion: Callable[[], T]) -> T:
    """Ejecuta una operación de base de datos reintentando si Neon está dormida.

    `pool_pre_ping` no cubre este caso: el problema no es una conexión rancia del
    pool sino que **abrir** una conexión nueva contra un endpoint suspendido
    falla mientras arranca. Sin reintento, la primera visita a la aplicación tras
    un rato de inactividad devolvía 503 y la pantalla de países salía vacía.

    Sólo reintenta errores de conexión (`OperationalError`, `DBAPIError` con
    `connection_invalidated`). Un error de SQL o de permisos falla a la primera:
    reintentarlo sería esconder el fallo real.
    """
    espera = ESPERA_INICIAL_S
    ultimo: Exception | None = None

    for intento in range(1, REINTENTOS + 1):
        try:
            return operacion()
        except (OperationalError, DBAPIError) as exc:
            recuperable = isinstance(exc, OperationalError) or getattr(
                exc, "connection_invalidated", False
            )
            if not recuperable or intento == REINTENTOS:
                raise
            ultimo = exc
            logger.warning(
                "Base de datos no disponible (intento %d/%d), reintentando en %.1fs: %s",
                intento, REINTENTOS, espera, exc,
            )
            time.sleep(espera)
            espera *= 2

    # Inalcanzable: el bucle o devuelve o relanza.
    raise ultimo  # type: ignore[misc]
