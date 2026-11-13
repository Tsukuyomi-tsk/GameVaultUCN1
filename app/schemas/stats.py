"""Response schema for GET /admin/stats/popularity (Fase 4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PopularityEntry(BaseModel):
    # Una fila del ranking de popularidad: a que juego corresponde
    # (identificado por id, titulo y slug, para que el frontend no tenga
    # que hacer una consulta aparte solo para mostrar el nombre) y cuantas
    # veces aparece contado (deseos o compras, segun la lista).
    game_id: int
    title: str
    slug: str
    count: int


class PopularityStats(BaseModel):
    # Se devuelve el rango de fechas usado en la consulta (puede ser None
    # si el admin no filtro por fecha) para que la respuesta sea explicita
    # sobre que periodo esta mostrando, sin que el cliente tenga que
    # recordar que parametros mando.
    date_from: datetime | None
    date_to: datetime | None
    # Los dos rankings, cada uno ya ordenado de mayor a menor y limitado
    # al "top N" pedido por el admin.
    top_wishlisted: list[PopularityEntry]
    top_purchased: list[PopularityEntry]
