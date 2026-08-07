"""Shared pure matching for promotion targets."""

from dataforge.engines.promotion.models import ActivePromotion
from dataforge.generators.geography.models import Location
from dataforge.generators.products.models import Product
from dataforge.generators.promotions.models import PromotionTargetType


def promotion_matches_target(
    promotion: ActivePromotion,
    location: Location,
    product: Product,
) -> bool:
    """Return whether a promotion target includes a location-product pair."""
    if promotion.target_type is PromotionTargetType.GLOBAL:
        return True
    target = {
        PromotionTargetType.REGION: location.region_id,
        PromotionTargetType.LOCATION: location.id,
        PromotionTargetType.CATEGORY: product.category_id,
        PromotionTargetType.PRODUCT: product.id,
    }[promotion.target_type]
    return target in promotion.target_ids
