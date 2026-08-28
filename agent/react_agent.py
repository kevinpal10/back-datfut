"""Agente "Profe KevBot" (entrenador táctico): bucle ReAct sobre AWS Bedrock.

Pensamiento → Acción → Observación (SPEC §4.2). Se escribe el bucle a mano en
lugar de usar el *tool runner* del SDK porque cada iteración tiene que quedar
registrada con sus argumentos y su latencia para la tabla `agent_runs`
(SPEC §5.5, caso de uso 2.2.3), y porque la rutina final la arma el backend a
partir de la observación de la herramienta, no del texto del modelo.

Si no hay credenciales de AWS, el endpoint **no cae**: degrada a una respuesta
determinista construida con las mismas herramientas (`run_sin_modelo`). Sin
modelo no hay análisis en lenguaje natural, pero las cifras y la rutina siguen
siendo reales — que es la garantía que importa.
"""

import re
import time
from typing import Any, Optional

from agent.tools import (
    MAX_MINUTOS,
    MIN_MINUTOS,
    TOOL_SCHEMAS,
    execute_tool,
    obtener_metricas_jugador,
    sugerir_entrenamiento,
)
from config import (
    AWS_REGION,
    BEDROCK_CLIENT,
    BEDROCK_MODEL_ID,
    bedrock_is_configured,
)
from core.positions import normalize_es

# Tope de vueltas del bucle. Con dos herramientas, tres iteraciones bastan;
# el tope existe para que un modelo que insista en llamar herramientas no deje
# la petición colgada.
MAX_ITERATIONS = 6

MAX_TOKENS = 16000

SYSTEM_PROMPT = """\
Eres **Profe KevBot**, el entrenador táctico de FutAnalytica AI. Ayudas a futbolistas amateurs a \
entrenar inspirándose en jugadores profesionales reales.

Reglas que no puedes romper:

1. NUNCA inventes una cifra. Goles, asistencias, minutos, porcentajes y ratings \
sólo pueden salir de la herramienta `obtener_metricas_jugador`. Si no la has \
llamado, no menciones números.
2. Llama a `obtener_metricas_jugador` ANTES de emitir cualquier juicio técnico \
sobre el jugador.
3. Si la herramienta responde `encontrado: false`, dilo explícitamente al \
usuario ("no logré recuperar las estadísticas de este jugador") y ofrécele una \
rutina genérica para su posición. No rellenes el hueco con estimaciones.
4. Los ejercicios salen exclusivamente de `sugerir_entrenamiento`. No inventes \
ejercicios, no cambies sus duraciones y no añadas bloques extra.
5. Cuando cites una cifra, di de qué competición y temporada sale.

Responde en español, en tono cercano y directo, sin listas interminables. \
Explica primero qué dicen los datos y después por qué la rutina encaja con \
ellos."""


class AgentUnavailable(RuntimeError):
    """El modelo no está disponible (sin credenciales o sin SDK instalado)."""


# ── Utilidades compartidas por ambos modos ───────────────────────────────────


def extraer_minutos(mensaje: str) -> Optional[int]:
    """Lee "tengo 30 minutos" del mensaje del usuario.

    Sólo se usa en el modo degradado: con modelo, es él quien decide el valor
    del argumento y el código se limita a validarlo.
    """
    # El lookbehind evita que el motor retroceda y lea "000" dentro de "1000".
    match = re.search(r"(?<!\d)(\d{1,4})\s*(?:minutos|minuto|min)(?![a-z])",
                      mensaje, flags=re.IGNORECASE)
    if not match:
        return None
    minutos = int(match.group(1))
    if minutos < MIN_MINUTOS:
        return None
    return min(minutos, MAX_MINUTOS)


def _validar_rutina(rutina: dict) -> dict:
    """Recorta la rutina si por lo que sea excede el tiempo declarado.

    SPEC §5.3: "la suma de los ejercicios nunca supera `tiempo_minutos`. Lo
    valida el backend; no se delega en el modelo". `sugerir_entrenamiento` ya lo
    garantiza; esta función es la segunda cerradura, por si la rutina llegara a
    construirse por otra vía.
    """
    limite = rutina.get("tiempo_minutos") or 0
    acumulado = 0
    ejercicios = []
    for ejercicio in rutina.get("ejercicios") or []:
        duracion = int(ejercicio.get("duracion_min") or 0)
        if acumulado + duracion > limite:
            continue
        acumulado += duracion
        ejercicios.append(ejercicio)
    rutina["ejercicios"] = ejercicios
    rutina["minutos_asignados"] = acumulado
    return rutina


def _rutina_desde_observacion(observacion: dict) -> Optional[dict]:
    """Convierte la salida de `sugerir_entrenamiento` en el campo `routine`."""
    if not isinstance(observacion, dict) or not observacion.get("ok"):
        return None
    return _validar_rutina(
        {
            "posicion": observacion["posicion"],
            "tiempo_minutos": observacion["tiempo_minutos"],
            "ejercicios": observacion["ejercicios"],
        }
    )


# ── Modo con modelo (Bedrock) ────────────────────────────────────────────────


def _build_client():
    """Cliente de Bedrock según `BEDROCK_CLIENT`, no según lo que traiga el SDK.

    Antes esta función prefería `AnthropicBedrockMantle` cuando la clase existía.
    Eso rompe en cuanto el SDK se actualiza: Mantle es un endpoint **con
    habilitación propia**, así que una cuenta con acceso normal a Bedrock empieza
    a recibir 403/404 sin haber tocado nada, y encima el formato de
    `BEDROCK_MODEL_ID` cambia entre ambos clientes (ver `config.py`).
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise AgentUnavailable(
            "Falta el paquete `anthropic[bedrock]`. Instálalo con "
            "`pip install -r requirements.txt`."
        ) from exc

    if BEDROCK_CLIENT == "mantle":
        mantle = getattr(anthropic, "AnthropicBedrockMantle", None)
        if mantle is None:
            raise AgentUnavailable(
                "BEDROCK_CLIENT=mantle pero el SDK `anthropic` instalado no trae "
                "`AnthropicBedrockMantle`. Actualiza el paquete o usa "
                "BEDROCK_CLIENT=invoke."
            )
        return mantle(aws_region=AWS_REGION)

    return anthropic.AnthropicBedrock(aws_region=AWS_REGION)


def run_con_modelo(
    mensaje: str,
    player_id: Optional[int],
    season: int,
    historial: Optional[list] = None,
) -> dict:
    """Ejecuta el bucle ReAct completo contra Bedrock."""
    if not bedrock_is_configured():
        raise AgentUnavailable(
            "No hay credenciales de AWS en el entorno para invocar Bedrock."
        )

    client = _build_client()

    contexto = (
        f"[Contexto de la ficha abierta: player_id={player_id}, season={season}]"
        if player_id
        else f"[Contexto: sin jugador seleccionado, season={season}]"
    )
    messages: list[dict] = list(historial or [])
    messages.append({"role": "user", "content": f"{contexto}\n\n{mensaje}"})

    tool_calls: list[dict] = []
    rutina: Optional[dict] = None
    texto_final = ""
    started = time.perf_counter()

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=BEDROCK_MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason == "refusal":
            raise AgentUnavailable("El modelo declinó responder a esta petición.")

        if response.stop_reason != "tool_use":
            texto_final = "".join(
                block.text for block in response.content if block.type == "text"
            )
            break

        messages.append({"role": "assistant", "content": response.content})

        resultados = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_started = time.perf_counter()
            observacion = execute_tool(block.name, dict(block.input))
            elapsed_ms = int((time.perf_counter() - tool_started) * 1000)

            tool_calls.append(
                {
                    "tool": block.name,
                    "input": dict(block.input),
                    "latency_ms": elapsed_ms,
                }
            )

            if block.name == "sugerir_entrenamiento":
                candidata = _rutina_desde_observacion(observacion)
                if candidata:
                    rutina = candidata

            resultados.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _as_text(observacion),
                }
            )

        # Todos los resultados van en un único mensaje de usuario: repartirlos
        # entre varios enseña al modelo a dejar de pedir herramientas en paralelo.
        messages.append({"role": "user", "content": resultados})
    else:
        texto_final = (
            "Me quedé sin margen para completar el análisis. Vuelve a intentarlo "
            "concretando la posición y los minutos de que dispones."
        )

    return {
        "agent_response": texto_final.strip(),
        "routine": rutina,
        "sources": [
            {"tool": call["tool"], **call["input"]} for call in tool_calls
        ],
        "tool_calls": tool_calls,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "model": BEDROCK_MODEL_ID,
        "degradado": False,
    }


def _as_text(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)


# ── Modo degradado (sin modelo) ──────────────────────────────────────────────


def run_sin_modelo(
    mensaje: str,
    player_id: Optional[int],
    season: int,
    motivo: str,
) -> dict:
    """Respuesta determinista: mismas herramientas, sin lenguaje natural generado.

    No inventa nada porque no hay nada generado: las cifras salen de la
    herramienta y el texto es una plantilla.
    """
    started = time.perf_counter()
    tool_calls: list[dict] = []
    partes: list[str] = []
    posicion: Optional[str] = None

    metricas = None
    if player_id:
        tool_started = time.perf_counter()
        metricas = obtener_metricas_jugador(player_id, season)
        tool_calls.append(
            {
                "tool": "obtener_metricas_jugador",
                "input": {"player_id": player_id, "season": season},
                "latency_ms": int((time.perf_counter() - tool_started) * 1000),
            }
        )

        if metricas.get("encontrado"):
            posicion = metricas.get("posicion")
            principal = next(
                (c for c in metricas["competiciones"] if c.get("partidos")),
                None,
            )
            if principal:
                partes.append(
                    f"{metricas['nombre']} disputó {principal['partidos']} partidos "
                    f"en {principal['competicion']} ({season})"
                    + (
                        f", con {principal['goles']} goles y {principal['asistencias']} asistencias."
                        if principal.get("goles") is not None
                        else "."
                    )
                )
        else:
            partes.append(
                "No logré recuperar las estadísticas de este jugador, pero puedo "
                "sugerirte un entrenamiento general para su posición."
            )

    # Sin posición conocida se cae a mediocampista, la más transversal.
    posicion = normalize_es(posicion) or "mediocampista"
    minutos = extraer_minutos(mensaje) or 30

    tool_started = time.perf_counter()
    observacion = sugerir_entrenamiento(posicion, minutos)
    tool_calls.append(
        {
            "tool": "sugerir_entrenamiento",
            "input": {"posicion": posicion, "minutos_disponibles": minutos},
            "latency_ms": int((time.perf_counter() - tool_started) * 1000),
        }
    )
    rutina = _rutina_desde_observacion(observacion)

    if rutina:
        partes.append(
            f"Te propongo una rutina de {rutina['minutos_asignados']} minutos "
            f"para {posicion}, dentro de los {minutos} que indicaste."
        )
    partes.append(
        "(El análisis en lenguaje natural está desactivado: "
        f"{motivo}. Las cifras y los ejercicios son reales.)"
    )

    return {
        "agent_response": " ".join(partes),
        "routine": rutina,
        "sources": [
            {"tool": call["tool"], **call["input"]} for call in tool_calls
        ],
        "tool_calls": tool_calls,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "model": None,
        "degradado": True,
    }
