"""Attribution — pure helpers for matching orders to the Elevate actions that
drove them.

An order can carry more than one promo id (a product-level flash_sale AND an
order-level recovery_offer stack), so `OrderDB.promo_applied` is a ", "-joined
list. Matching a single `action.promo_id` against that whole string silently
dropped every stacked order from attribution — revenue landed but was never
tagged, and the learning loop mis-read it as "no conversion". These helpers split
the joined value so a stacked order is attributed to EVERY contributing action,
while the store total counts each order only once.

Pure — no I/O. Used by dashboard.py and outcome_observer.py.
"""
from __future__ import annotations

from typing import Iterable

# Must match how orders.py writes the column: ", ".join(sorted(set(promo_ids))).
_SEP = ","


def promo_ids_of(promo_applied: str | None) -> list[str]:
    """Split a ", "-joined `promo_applied` value into its individual promo ids."""
    if not promo_applied:
        return []
    return [p.strip() for p in promo_applied.split(_SEP) if p.strip()]


def attribute_orders(orders: Iterable, action_promo_ids: Iterable[str]) -> dict[str, list]:
    """Map each action promo_id → the orders whose `promo_applied` contains it.

    A stacked order (two promos) is attributed to every action that contributed
    to it. Every requested promo_id gets a key (empty list if nothing matched).
    """
    by_promo: dict[str, list] = {}
    for order in orders:
        for pid in promo_ids_of(getattr(order, "promo_applied", None)):
            by_promo.setdefault(pid, []).append(order)
    return {pid: by_promo.get(pid, []) for pid in action_promo_ids}


def total_attributed_gmv(attributed: dict[str, list]) -> float:
    """Sum the GMV of the DISTINCT attributed orders — so an order matched by two
    actions (a stacked flash_sale + recovery) is counted once, not twice."""
    seen: dict[object, float] = {}
    for orders in attributed.values():
        for order in orders:
            key = getattr(order, "id", None) or id(order)
            seen[key] = float(getattr(order, "total", 0.0))
    return round(sum(seen.values()), 2)
