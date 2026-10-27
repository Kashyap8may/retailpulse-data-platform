"""Source 1: the e-commerce and ERP database (RDS PostgreSQL).

Writes one CSV per table showing the database exactly as it looks at ``as_of``: rows are
updated in place, so an order shows only its latest status, and a customer who moved shows
only the new address. Capturing that history is the pipeline's job (bronze snapshots and
SCD Type 2 in silver), just like with a real OLTP system.

The table definitions live in ``postgres_schema.sql`` next to this file.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..activity.simulation import SimulationResult, status_as_of
from ..master import MasterData
from .common import public, write_csv

TABLE_COLUMNS = {
    "product_categories": [
        "category_id",
        "parent_category_id",
        "category_name",
        "category_level",
        "created_at",
        "updated_at",
    ],
    "brands": ["brand_id", "brand_name", "primary_department", "created_at", "updated_at"],
    "suppliers": [
        "supplier_id",
        "supplier_name",
        "country_code",
        "lead_time_days",
        "contact_email",
        "created_at",
        "updated_at",
    ],
    "products": [
        "product_id",
        "sku",
        "product_name",
        "category_id",
        "brand_id",
        "supplier_id",
        "vendor_sku",
        "unit_cost_usd",
        "list_price_usd",
        "weight_kg",
        "is_active",
        "created_at",
        "updated_at",
    ],
    "stores": [
        "store_id",
        "store_name",
        "store_type",
        "city",
        "region",
        "country_code",
        "timezone",
        "opened_date",
        "floor_area_sqm",
        "created_at",
        "updated_at",
    ],
    "warehouses": ["warehouse_id", "warehouse_name", "city", "country_code", "created_at", "updated_at"],
    "loyalty_tiers": ["tier_code", "tier_name", "min_lifetime_spend_usd", "discount_pct"],
    "customers": [
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "address_line1",
        "city",
        "postal_code",
        "country_code",
        "loyalty_card_no",
        "loyalty_tier",
        "marketing_opt_in",
        "created_at",
        "updated_at",
    ],
    "orders": [
        "order_id",
        "order_number",
        "customer_id",
        "order_ts",
        "channel",
        "status",
        "currency",
        "shipping_service",
        "ship_to_city",
        "ship_to_postal_code",
        "ship_to_country",
        "fulfilment_warehouse_id",
        "subtotal_amount",
        "discount_amount",
        "shipping_amount",
        "tax_amount",
        "total_amount",
        "created_at",
        "updated_at",
    ],
    "order_items": [
        "order_item_id",
        "order_id",
        "line_number",
        "product_id",
        "quantity",
        "unit_price",
        "discount_amount",
        "promotion_id",
        "created_at",
        "updated_at",
    ],
    "payments": [
        "payment_id",
        "order_id",
        "payment_method",
        "payment_type",
        "status",
        "amount",
        "currency",
        "provider_reference",
        "created_at",
        "updated_at",
    ],
    "returns": [
        "return_id",
        "order_id",
        "order_item_id",
        "quantity",
        "reason_code",
        "status",
        "refund_amount",
        "currency",
        "created_at",
        "updated_at",
    ],
}

# Tables in an order that satisfies foreign keys.
LOAD_ORDER = list(TABLE_COLUMNS)


def _with_status(records: list[dict], as_of: datetime):
    for rec in records:
        seen = status_as_of(rec["_events"], as_of)
        if seen is None:
            continue
        row = public(rec)
        row["status"], row["updated_at"] = seen
        row["created_at"] = rec["_events"][0][0]
        yield row


def postgres_tables(md: MasterData, sim: SimulationResult, as_of: datetime) -> dict[str, list[dict]]:
    """Every table's rows as the database holds them at ``as_of``."""
    latest_customer: dict[int, dict] = {}
    for version in sim.customer_versions:
        if version["created_at"] <= as_of and version["updated_at"] <= as_of:
            latest_customer[version["customer_id"]] = version
    order_ids = set()
    orders = []
    for row in _with_status(sim.orders, as_of):
        order_ids.add(row["order_id"])
        orders.append(row)
    return {
        "product_categories": md.categories,
        "brands": md.brands,
        "suppliers": [public(s) for s in md.suppliers],
        "products": [public(p) for p in md.products],
        "stores": md.stores,
        "warehouses": md.warehouses,
        "loyalty_tiers": md.loyalty_tiers,
        "customers": sorted(latest_customer.values(), key=lambda c: c["customer_id"]),
        "orders": orders,
        "order_items": [i for i in sim.order_items if i["order_id"] in order_ids],
        "payments": list(_with_status(sim.payments, as_of)),
        "returns": list(_with_status(sim.returns, as_of)),
    }


def write_postgres(md: MasterData, sim: SimulationResult, out_dir: Path, as_of: datetime) -> dict[str, int]:
    counts = {}
    for table, rows in postgres_tables(md, sim, as_of).items():
        counts[table] = write_csv(out_dir / "postgres" / f"{table}.csv", TABLE_COLUMNS[table], rows)
    return counts
