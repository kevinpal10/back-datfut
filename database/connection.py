from sqlalchemy import create_engine

from config import DATABASE_URL

# Neon es Postgres serverless: corta las conexiones ociosas por su cuenta. Sin
# estas dos opciones, SQLAlchemy entrega del pool una conexión ya muerta y la
# operación falla con "SSL connection has been closed unexpectedly". Se veía en
# cada guardado de rutina: el chat respondía igual (el error está capturado),
# pero el historial se perdía en silencio.
#
#   pool_pre_ping → comprueba la conexión con un SELECT 1 antes de entregarla y
#                   la reabre de forma transparente si está muerta.
#   pool_recycle  → la descarta antes de que Neon la cierre por inactividad.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)
