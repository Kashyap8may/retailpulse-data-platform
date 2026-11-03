from datetime import date

import pytest

from data_generator.publish import batches, target_for, upsert_sql

DAY = date(2026, 7, 2)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("days/2026-07-02/postgres/orders.csv", ("postgres", "orders")),
        ("days/2026-07-02/carrier_api/shipments.jsonl", ("shipments", "")),
        (
            "days/2026-07-02/s3/pos_sales/landing_date=2026-07-02/pos_ST001_20260701.csv",
            ("s3", "pos_sales/landing_date=2026-07-02/pos_ST001_20260701.csv"),
        ),
        (
            "days/2026-07-02/sftp/3pl/inventory/INV_WH-DE_20260702.psv",
            ("sftp", "3pl/inventory/INV_WH-DE_20260702.psv"),
        ),
    ],
)
def test_objects_map_to_their_source(key, expected):
    assert target_for(key, DAY) == expected


def test_unknown_objects_are_rejected():
    with pytest.raises(ValueError):
        target_for("days/2026-07-02/elsewhere/x.csv", DAY)


def test_upsert_updates_every_column_but_the_key():
    sql = upsert_sql("brands", ["brand_id", "brand_name", "updated_at"], "staging_brands")
    assert "ON CONFLICT (brand_id)" in sql
    assert "brand_name = EXCLUDED.brand_name, updated_at = EXCLUDED.updated_at" in sql
    assert "brand_id = EXCLUDED" not in sql


def test_batches_keep_order_and_cover_every_day():
    days = list(range(70))
    assert [len(b) for b in batches(days, 31)] == [31, 31, 8]
    assert sum(batches(days, 31), []) == days
