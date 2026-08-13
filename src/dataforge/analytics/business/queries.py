"""Readable DuckDB SQL for the first supported business questions."""

from enum import StrEnum


class BusinessQuery(StrEnum):
    REVENUE_BY_LOCATION = "revenue_by_location"
    PRODUCT_PERFORMANCE = "product_performance"
    CATEGORY_PERFORMANCE = "category_performance"
    DAILY_SALES = "daily_sales"
    MONTHLY_SALES = "monthly_sales"
    LOST_SALES_BY_PRODUCT = "lost_sales_by_product"
    LOST_SALES_BY_LOCATION = "lost_sales_by_location"
    LOST_SALES_BY_PRODUCT_LOCATION = "lost_sales_by_product_location"
    LOST_SALES_BY_REASON = "lost_sales_by_reason"
    CUSTOMER_PURCHASE_ANALYSIS = "customer_purchase_analysis"
    CHANNEL_PERFORMANCE = "channel_performance"
    REPLENISHMENT_PERFORMANCE = "replenishment_performance"
    INVENTORY_MOVEMENT_SUMMARY = "inventory_movement_summary"
    INVENTORY_MOVEMENT_BY_PRODUCT = "inventory_movement_by_product"
    INVENTORY_MOVEMENT_BY_LOCATION = "inventory_movement_by_location"
    PROMOTED_SALES_SUMMARY = "promoted_sales_summary"
    PROMOTION_ASSOCIATED_SALES = "promotion_associated_sales"


QUERIES: dict[BusinessQuery, str] = {
    BusinessQuery.REVENUE_BY_LOCATION: """
        SELECT
            l.location_id,
            l.location_name,
            l.city_name,
            s.currency,
            SUM(s.net_sales_amount) AS net_sales,
            SUM(s.gross_sales_amount) AS gross_sales,
            SUM(s.discount_amount) AS discount_amount,
            SUM(s.completed_quantity) AS completed_units,
            COUNT(DISTINCT CASE
                WHEN s.completed_quantity > 0 THEN s.basket_id
            END) AS completed_baskets
        FROM fact_sales AS s
        JOIN dim_location AS l USING (location_id)
        GROUP BY l.location_id, l.location_name, l.city_name, s.currency
        ORDER BY net_sales DESC, l.location_id, s.currency
    """,
    BusinessQuery.PRODUCT_PERFORMANCE: """
        SELECT
            p.product_id,
            p.product_name,
            p.category_id,
            p.category_name,
            s.currency,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.net_sales_amount) AS net_sales,
            SUM(s.rejected_quantity) AS rejected_units,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_product AS p USING (product_id)
        GROUP BY p.product_id, p.product_name, p.category_id, p.category_name,
                 s.currency
        ORDER BY net_sales DESC, p.product_id, s.currency
    """,
    BusinessQuery.CATEGORY_PERFORMANCE: """
        SELECT
            p.category_id,
            p.category_name,
            s.currency,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.net_sales_amount) AS net_sales,
            SUM(s.rejected_quantity) AS rejected_units,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_product AS p USING (product_id)
        GROUP BY p.category_id, p.category_name, s.currency
        ORDER BY net_sales DESC, p.category_id, s.currency
    """,
    BusinessQuery.DAILY_SALES: """
        SELECT
            d.date,
            d.year,
            d.month_number,
            d.month_name,
            s.currency,
            SUM(s.net_sales_amount) AS net_sales,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.rejected_quantity) AS rejected_units,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_date AS d USING (date)
        GROUP BY d.date, d.year, d.month_number, d.month_name, s.currency
        ORDER BY d.date, s.currency
    """,
    BusinessQuery.MONTHLY_SALES: """
        SELECT
            d.year,
            d.month_number,
            d.month_name,
            s.currency,
            SUM(s.net_sales_amount) AS net_sales,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.rejected_quantity) AS rejected_units,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_date AS d USING (date)
        GROUP BY d.year, d.month_number, d.month_name, s.currency
        ORDER BY d.year, d.month_number, s.currency
    """,
    BusinessQuery.LOST_SALES_BY_PRODUCT: """
        SELECT
            p.product_id,
            p.product_name,
            p.category_name,
            s.currency,
            SUM(s.rejected_quantity) AS rejected_quantity,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_product AS p USING (product_id)
        WHERE s.rejected_quantity > 0
        GROUP BY p.product_id, p.product_name, p.category_name, s.currency
        ORDER BY lost_sales DESC, p.product_id, s.currency
    """,
    BusinessQuery.LOST_SALES_BY_LOCATION: """
        SELECT
            l.location_id,
            l.location_name,
            l.city_name,
            s.currency,
            SUM(s.rejected_quantity) AS rejected_quantity,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_location AS l USING (location_id)
        WHERE s.rejected_quantity > 0
        GROUP BY l.location_id, l.location_name, l.city_name, s.currency
        ORDER BY lost_sales DESC, l.location_id, s.currency
    """,
    BusinessQuery.LOST_SALES_BY_PRODUCT_LOCATION: """
        SELECT
            p.product_id,
            p.product_name,
            l.location_id,
            l.location_name,
            s.currency,
            SUM(s.rejected_quantity) AS rejected_quantity,
            SUM(s.lost_sales_amount) AS lost_sales
        FROM fact_sales AS s
        JOIN dim_product AS p USING (product_id)
        JOIN dim_location AS l USING (location_id)
        WHERE s.rejected_quantity > 0
        GROUP BY p.product_id, p.product_name, l.location_id, l.location_name,
                 s.currency
        ORDER BY lost_sales DESC, p.product_id, l.location_id, s.currency
    """,
    BusinessQuery.LOST_SALES_BY_REASON: """
        SELECT
            rejection_reason,
            currency,
            SUM(rejected_quantity) AS rejected_quantity,
            SUM(lost_sales_amount) AS lost_sales
        FROM fact_sales
        WHERE rejected_quantity > 0
        GROUP BY rejection_reason, currency
        ORDER BY lost_sales DESC, rejection_reason, currency
    """,
    BusinessQuery.CUSTOMER_PURCHASE_ANALYSIS: """
        SELECT
            c.customer_id,
            c.segment,
            c.preferred_channel,
            c.purchase_frequency,
            s.currency,
            COUNT(DISTINCT s.basket_id) AS basket_count,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.net_sales_amount) AS net_sales
        FROM fact_sales AS s
        JOIN dim_customer AS c USING (customer_id)
        GROUP BY c.customer_id, c.segment, c.preferred_channel,
                 c.purchase_frequency, s.currency
        ORDER BY net_sales DESC, c.customer_id, s.currency
    """,
    BusinessQuery.CHANNEL_PERFORMANCE: """
        SELECT
            channel,
            currency,
            COUNT(DISTINCT basket_id) AS baskets,
            COUNT(DISTINCT customer_id) AS customers,
            SUM(completed_quantity) AS completed_units,
            SUM(net_sales_amount) AS net_sales,
            SUM(lost_sales_amount) AS lost_sales
        FROM fact_sales
        GROUP BY channel, currency
        ORDER BY net_sales DESC, channel, currency
    """,
    BusinessQuery.REPLENISHMENT_PERFORMANCE: """
        SELECT
            COUNT(*) AS requested_count,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
            COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
            SUM(requested_quantity) AS requested_quantity,
            COALESCE(SUM(received_quantity), 0) AS received_quantity,
            CASE WHEN COUNT(*) = 0 THEN 0
                 ELSE COUNT(*) FILTER (WHERE status = 'completed')::DOUBLE
                      / COUNT(*)
            END AS completion_rate,
            AVG(completed_tick_index - requested_tick_index)
                FILTER (WHERE status = 'completed') AS avg_completion_lead_ticks
        FROM fact_replenishment
    """,
    BusinessQuery.INVENTORY_MOVEMENT_SUMMARY: """
        SELECT
            movement_type,
            COUNT(*) AS movement_count,
            SUM(CASE WHEN movement_type = 'sale' THEN quantity ELSE 0 END)
                AS quantity_removed_by_sales,
            SUM(CASE WHEN movement_type = 'replenishment' THEN quantity ELSE 0 END)
                AS quantity_received_by_replenishment
        FROM fact_inventory_movement
        GROUP BY movement_type
        ORDER BY movement_type
    """,
    BusinessQuery.INVENTORY_MOVEMENT_BY_PRODUCT: """
        SELECT
            p.product_id,
            p.product_name,
            m.movement_type,
            COUNT(*) AS movement_count,
            SUM(m.quantity) AS quantity
        FROM fact_inventory_movement AS m
        JOIN dim_product AS p USING (product_id)
        GROUP BY p.product_id, p.product_name, m.movement_type
        ORDER BY p.product_id, m.movement_type
    """,
    BusinessQuery.INVENTORY_MOVEMENT_BY_LOCATION: """
        SELECT
            l.location_id,
            l.location_name,
            l.city_name,
            m.movement_type,
            COUNT(*) AS movement_count,
            SUM(m.quantity) AS quantity
        FROM fact_inventory_movement AS m
        JOIN dim_location AS l USING (location_id)
        GROUP BY l.location_id, l.location_name, l.city_name, m.movement_type
        ORDER BY l.location_id, m.movement_type
    """,
    BusinessQuery.PROMOTED_SALES_SUMMARY: """
        WITH promoted_lines AS (
            SELECT DISTINCT transaction_line_id
            FROM bridge_sales_promotion
        )
        SELECT
            s.currency,
            COUNT(*) AS associated_sales_lines,
            COUNT(DISTINCT s.basket_id) AS distinct_baskets,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.net_sales_amount) AS associated_net_sales
        FROM promoted_lines AS b
        JOIN fact_sales AS s USING (transaction_line_id)
        GROUP BY s.currency
        ORDER BY s.currency
    """,
    BusinessQuery.PROMOTION_ASSOCIATED_SALES: """
        SELECT
            p.promotion_id,
            p.name AS promotion_name,
            s.currency,
            COUNT(*) AS associated_sales_lines,
            COUNT(DISTINCT s.basket_id) AS distinct_baskets,
            SUM(s.completed_quantity) AS completed_units,
            SUM(s.net_sales_amount) AS associated_net_sales
        FROM bridge_sales_promotion AS b
        JOIN fact_sales AS s USING (transaction_line_id)
        JOIN dim_promotion AS p USING (promotion_id)
        GROUP BY p.promotion_id, p.name, s.currency
        ORDER BY associated_net_sales DESC, p.promotion_id, s.currency
    """,
}


__all__ = ["BusinessQuery", "QUERIES"]
