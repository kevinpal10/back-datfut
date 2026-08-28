"""Configuración común de las pruebas.

Las credenciales se fijan a valores falsos ANTES de que `config.py` se importe,
para que la suite no dependa del `.env` real ni toque servicios externos.
`load_dotenv` no pisa variables ya presentes en el entorno, así que basta con
ponerlas aquí.
"""

import os

os.environ.setdefault("FOOTBALL_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost/test")
os.environ.setdefault("DEFAULT_SEASON", "2024")
