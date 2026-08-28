"""Temporada por defecto del sistema.

Antes convivían dos valores distintos en el mismo flujo (`2026` al navegar desde
el país, `2024` al abrir la ficha), así que la ficha podía pedir una temporada
que no era la elegida. SPEC §4.1: la temporada viaja en la navegación y debe ser
la misma en todos los saltos; esta constante es sólo el respaldo para cuando no
llega ninguna.

El frontend tiene su espejo en `datfut/src/app/core/season.ts`. Si se cambia una,
se cambia la otra.
"""

import os

# Coincide con el ejemplo del contrato en SPEC §5.2.
DEFAULT_SEASON = int(os.getenv("DEFAULT_SEASON", "2024"))
