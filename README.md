# Backend — FutAnalytica AI

BFF en FastAPI sobre `api-football` v3, con caché de 24 h, catálogo de países en
PostgreSQL (Neon) y el agente "Entrenador Táctico" sobre AWS Bedrock.

La especificación del producto está en [`../SPEC.md`](../SPEC.md); el estado real
y la deuda pendiente, en [`../ESTADO.md`](../ESTADO.md).

## Arranque

```bash
cd back_fut_analisis

python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash); en Linux/macOS: .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env                # y completa FOOTBALL_API_KEY y DATABASE_URL

uvicorn main:app --reload           # http://127.0.0.1:8000
```

Documentación interactiva en `http://127.0.0.1:8000/docs`.

`config.py` falla al arrancar con un mensaje explícito si falta
`FOOTBALL_API_KEY` o `DATABASE_URL`: si ves ese error, es que falta el `.env`, no
que haya un fallo de código. Las credenciales **sólo** viven ahí; `.env` está
ignorado por git.

## Comprobar que está vivo

```bash
curl http://127.0.0.1:8000/health
```

Devuelve el estado de la caché y si el agente corre con modelo o degradado:

```json
{
  "status": "ok",
  "cache": { "entries": 12, "fresh": 12, "stale": 0, "ttl_seconds": 86400 },
  "agent": { "bedrock_configurado": false, "modo": "degradado" }
}
```

## Pruebas

```bash
python -m pytest              # toda la suite
python -m pytest -k rutina    # un subconjunto
python -m pytest tests/test_api.py::test_health_expone_cache_y_modo_del_agente
```

Ninguna prueba sale a la red ni toca PostgreSQL: `tests/conftest.py` fija
credenciales falsas y los tests sustituyen el cliente HTTP y la persistencia.

## Estructura

```
main.py                     app, routers, CORS y traducción de errores a HTTP
config.py                   único origen de credenciales y configuración
core/                       temporada por defecto, traducción de posiciones, helpers HTTP
clients/                    cliente de api-football, caché TTL y errores tipados
routes/                     routers finos, uno por dominio
services/                   lógica de cada dominio (métodos estáticos)
agent/                      catálogo de ejercicios, herramientas y bucle ReAct
database/                   engine de SQLAlchemy y persistencia del agente
tests/                      pytest
```

El flujo es siempre `routes → services → clients`. El cliente es el único punto
que habla con api-football: desenvuelve `response`, detecta cuota agotada o llave
inválida, cachea 24 h y sirve la última copia conocida si la API falla.

## El agente

`POST /agent/chat` funciona **con y sin** credenciales de AWS:

* **Con Bedrock** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`):
  ejecuta el bucle ReAct completo — el modelo llama a `obtener_metricas_jugador`
  y `sugerir_entrenamiento` antes de responder.
* **Sin credenciales**: degrada a una respuesta determinista construida con las
  mismas herramientas. No hay análisis en lenguaje natural, pero las cifras y los
  ejercicios siguen siendo reales. La respuesta lo indica con `"degraded": true`.

En ambos modos la duración total de la rutina **nunca** supera los minutos
pedidos: lo garantiza el código (`agent/tools.py`), no una instrucción al modelo.

Las tablas `routines` y `agent_runs` se crean solas al arrancar. Si la base no
responde, el backend arranca igual y el agente sigue contestando: se pierde el
historial, no la conversación.
