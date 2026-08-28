"""Caché en memoria con TTL para las respuestas de api-football.

Cumple dos objetivos del SPEC §6:

* **Cuota.** Una navegación repetida (volver atrás, reabrir una ficha) no vuelve
  a consumir peticiones de la API externa durante 24 h.
* **Tolerancia a fallos.** Las entradas no se borran al vencer el TTL: quedan
  como copia *rancia*. Si la API externa falla, se sirve esa copia en lugar de
  dejar la pantalla en blanco (SPEC §4.3).

Es deliberadamente un diccionario en memoria: se pierde al reiniciar el proceso
y no se comparte entre réplicas. Suficiente para un backend de una sola
instancia; migrar a Redis es un cambio localizado en esta clase.
"""

import threading
import time
from typing import Any, Optional, Tuple

# 24 horas, el valor que fija SPEC §6 ("Latencia y caché").
DEFAULT_TTL_SECONDS = 24 * 60 * 60

# Tope de entradas para que un backend de larga vida no crezca sin límite.
DEFAULT_MAX_ENTRIES = 512


class TtlCache:

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_fresh(self, key: str) -> Tuple[bool, Any]:
        """Devuelve `(True, valor)` sólo si la entrada existe y no ha vencido."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            stored_at, value = entry
            if time.time() - stored_at > self.ttl_seconds:
                return False, None
            return True, value

    def get_any(self, key: str) -> Tuple[bool, Any]:
        """Devuelve la entrada aunque haya vencido: el respaldo ante un fallo."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            return True, entry[1]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._entries) >= self.max_entries and key not in self._entries:
                # Desaloja la entrada más antigua; con 512 claves el coste es
                # irrelevante frente a una llamada HTTP.
                oldest = min(self._entries, key=lambda k: self._entries[k][0])
                del self._entries[oldest]
            self._entries[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict:
        """Usado por `GET /health` para ver el estado sin abrir el proceso."""
        with self._lock:
            now = time.time()
            fresh = sum(
                1 for stored_at, _ in self._entries.values()
                if now - stored_at <= self.ttl_seconds
            )
            return {
                "entries": len(self._entries),
                "fresh": fresh,
                "stale": len(self._entries) - fresh,
                "ttl_seconds": self.ttl_seconds,
            }


def build_key(endpoint: str, params: Optional[dict]) -> str:
    """Clave estable: mismo endpoint y mismos parámetros → misma clave."""
    if not params:
        return endpoint
    ordered = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{endpoint}?{ordered}"
