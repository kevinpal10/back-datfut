"""Configuración central del backend.

Todas las credenciales se leen de variables de entorno. Para desarrollo local,
copia `.env.example` a `.env` y completa los valores; `.env` está ignorado por git
y nunca debe subirse al repositorio.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Carga el .env que vive junto a este archivo (no depende del directorio actual).
load_dotenv(Path(__file__).resolve().parent / ".env")


def _required(name: str) -> str:
    """Devuelve la variable de entorno o falla al arrancar con un mensaje claro."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Falta la variable de entorno '{name}'. "
            "Copia back_fut_analisis/.env.example a back_fut_analisis/.env "
            "y completa el valor antes de arrancar el servidor."
        )
    return value


# Llave de api-football (https://dashboard.api-football.com) — cabecera x-apisports-key.
FOOTBALL_API_KEY = _required("FOOTBALL_API_KEY")

# Cadena de conexión a PostgreSQL (Neon), con usuario y contraseña.
DATABASE_URL = _required("DATABASE_URL")

# Base de api-football; configurable por si se cambia de plan o de host.
FOOTBALL_API_BASE_URL = os.getenv(
    "FOOTBALL_API_BASE_URL", "https://v3.football.api-sports.io"
)

# Orígenes permitidos por CORS, separados por comas. En desarrollo se deja "*";
# SPEC §6 exige restringirlo al dominio del frontend antes de desplegar.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

# ── Agente "Entrenador Táctico" (AWS Bedrock) ────────────────────────────────
# Opcionales: sin ellas el agente sigue respondiendo, pero degradado a rutinas
# deterministas del catálogo, sin análisis en lenguaje natural (SPEC §3, Módulo 3).
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Qué cliente del SDK usar para hablar con Bedrock. Son dos endpoints distintos,
# con catálogos y habilitaciones **separados**:
#
#   · "invoke" → AnthropicBedrock, la ruta bedrock-runtime InvokeModel. Usa el id
#     de un *inference profile*: `us.anthropic.claude-sonnet-4-6`.
#   · "mantle" → AnthropicBedrockMantle, el endpoint Messages. Usa ids sin
#     prefijo de región: `anthropic.claude-opus-5`. Requiere habilitación propia;
#     tener acceso al modelo en la consola de Bedrock NO da acceso a Mantle.
#
# El default es "invoke" porque es el que responde con el acceso estándar de
# Bedrock. Elegirlo explícitamente evita que la disponibilidad de la clase en el
# SDK instalado decida por nosotros y el id deje de encajar.
BEDROCK_CLIENT = os.getenv("BEDROCK_CLIENT", "invoke").strip().lower()

# El formato depende de BEDROCK_CLIENT (ver arriba).
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-5")


def bedrock_is_configured() -> bool:
    """`True` si hay credenciales de AWS en el entorno para invocar Bedrock.

    boto3 admite varias fuentes (variables de entorno, perfil, rol de la
    instancia); aquí sólo se comprueba la más común para poder avisar en
    `/health` sin intentar una llamada real.
    """
    return bool(
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
        or os.getenv("AWS_ROLE_ARN")
        or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
    )
