import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from clients.errors import QUOTA_EXCEEDED, ApiFootballError, DatabaseError
from clients.football_api_client import football_client
from config import CORS_ORIGINS, bedrock_is_configured
from database import agent_store
from routes.agent import router as agent_router
from routes.country import router as country_router
from routes.leagues import router as leagues_router
from routes.players import router as player_router
from routes.statistics import legacy_router as statistics_legacy_router
from routes.statistics import router as statistics_router
from routes.teams import router as teams_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea `routines` y `agent_runs` si no existen. Si la base no responde, el
    # backend arranca igual: el explorador no la necesita y el agente degrada.
    if agent_store.ensure_schema():
        logger.info("Esquema del agente listo (routines, agent_runs).")
    yield


app = FastAPI(title="FutAnalytica AI — BFF", lifespan=lifespan)

app.include_router(teams_router)
app.include_router(country_router)
app.include_router(player_router)
app.include_router(statistics_router)
app.include_router(statistics_legacy_router)
app.include_router(leagues_router)
app.include_router(agent_router)

# `allow_credentials=True` junto a `allow_origins=["*"]` es una combinación que
# los navegadores rechazan; con comodín, las credenciales se desactivan.
allow_credentials = CORS_ORIGINS != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    # Sin esto el navegador no deja al frontend leer la marca de caché rancia.
    expose_headers=["X-Data-Stale"],
)


@app.exception_handler(ApiFootballError)
def handle_api_football_error(request: Request, exc: ApiFootballError):
    """SPEC §4.3: cuerpo tipado en lugar de un 500 opaco.

    Se llega aquí sólo cuando api-football falla **y** la caché no tenía ninguna
    copia previa que servir; si la tenía, la petición devolvió 200 con la
    cabecera `X-Data-Stale`.
    """
    logger.warning("api-football falló (%s): %s", exc.kind, exc.message)
    status_code = 503 if exc.kind == QUOTA_EXCEEDED else 502
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.kind, "cached": False, "message": exc.message},
    )


@app.exception_handler(DatabaseError)
def handle_database_error(request: Request, exc: DatabaseError):
    logger.error("Error de base de datos: %s", exc.message)
    return JSONResponse(
        status_code=503,
        content={"detail": "database_error", "message": exc.message},
    )


@app.get("/health", tags=["Health"])
def health():
    """Estado del proceso sin necesidad de abrirlo: caché y modo del agente."""
    return {
        "status": "ok",
        "cache": football_client.cache.stats(),
        "agent": {
            "bedrock_configurado": bedrock_is_configured(),
            "modo": "modelo" if bedrock_is_configured() else "degradado",
        },
    }
