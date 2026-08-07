"""Lookup operations for the active location-product assortment."""

from dataforge.generators.inventory.models import InventoryItem


def index_active_assortment(
    inventory: tuple[InventoryItem, ...],
) -> dict[tuple[str, str], InventoryItem]:
    """Index active inventory items by their commercial combination."""
    assortment: dict[tuple[str, str], InventoryItem] = {}
    for item in inventory:
        if not item.active:
            continue
        key = (item.location_id, item.product_id)
        if key in assortment:
            raise ValueError(
                "Multiple active InventoryItems exist for commercial combination: "
                f"{item.location_id}/{item.product_id}"
            )
        assortment[key] = item
    return assortment
