"""Errores tipados de la integración con api-football.

El backend nunca deja escapar un `KeyError` ni un cuerpo de error de la API
externa disfrazado de datos: todo fallo de `api-football` se convierte en una de
estas excepciones, y `main.py` las traduce a una respuesta HTTP con un `detail`
que el frontend puede interpretar (SPEC §4.3).
"""

# Valores posibles de `kind`. Viajan tal cual al frontend en el campo `detail`.
QUOTA_EXCEEDED = "quota_exceeded"
AUTH_ERROR = "auth_error"
UPSTREAM_ERROR = "upstream_error"


class ApiFootballError(RuntimeError):
    """Fallo al obtener datos de api-football.

    `kind` distingue el motivo para que el frontend pueda reaccionar distinto a
    una cuota agotada (reintentar mañana) que a una llave inválida (avisar al
    operador).
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class DatabaseError(RuntimeError):
    """Fallo al leer de PostgreSQL (catálogo de países)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
