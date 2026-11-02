import csv
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta

import pytest

from data_generator.config import GeneratorConfig
from data_generator.simulate import generate


def _read_csv(path):
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "_manifest.json"):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_same_seed_gives_identical_output(generated, small_cfg, tmp_path):
    out, _ = generated
    generate(small_cfg, tmp_path)
    assert _tree_hash(out) == _tree_hash(tmp_path)


def test_adding_a_day_never_changes_earlier_days(small_cfg, tmp_path):
    shorter, longer = tmp_path / "shorter", tmp_path / "longer"
    shorter.mkdir()
    longer.mkdir()
    # Same as_of, so the database and API views must match even though one run simulated more days.
    as_of = datetime.combine(small_cfg.end_date + timedelta(days=1), time.min, tzinfo=UTC)
    generate(small_cfg, shorter, as_of)
    generate(replace(small_cfg, days=small_cfg.days + 1), longer, as_of)
    for path in (p for p in shorter.rglob("*") if p.is_file() and p.name != "_manifest.json"):
        other = longer / path.relative_to(shorter)
        assert other.read_bytes() == path.read_bytes(), path.relative_to(shorter)


def test_days_cannot_exceed_the_horizon():
    with pytest.raises(ValueError):
        GeneratorConfig(days=366, horizon_days=365)


def test_every_source_has_data(generated):
    _, manifest = generated
    counts = manifest["counts"]
    for key in [
        "customers",
        "orders",
        "order_items",
        "payments",
        "shipments",
        "pos_lines",
        "inventory_files",
        "delivery_files",
        "promotion_exports",
    ]:
        assert counts[key] > 0, key


def test_postgres_foreign_keys_hold(generated):
    out, _ = generated
    pg = out / "postgres"
    products = {r["product_id"] for r in _read_csv(pg / "products.csv")}
    customers = {r["customer_id"]: r for r in _read_csv(pg / "customers.csv")}
    orders = {r["order_id"]: r for r in _read_csv(pg / "orders.csv")}
    items = _read_csv(pg / "order_items.csv")
    assert all(i["product_id"] in products for i in items)
    assert all(i["order_id"] in orders for i in items)
    for o in orders.values():
        assert o["customer_id"] in customers
        assert customers[o["customer_id"]]["created_at"] <= o["order_ts"]
    item_ids = {i["order_item_id"] for i in items}
    assert all(r["order_item_id"] in item_ids for r in _read_csv(pg / "returns.csv"))


def test_nothing_after_as_of(generated):
    out, manifest = generated
    as_of = datetime.fromisoformat(manifest["as_of"])
    for table in ["customers", "orders", "payments", "returns"]:
        for row in _read_csv(out / "postgres" / f"{table}.csv"):
            assert datetime.fromisoformat(row["updated_at"]) <= as_of


def test_shipments_match_orders(generated):
    out, _ = generated
    order_numbers = {r["order_number"] for r in _read_csv(out / "postgres" / "orders.csv")}
    with (out / "carrier_api" / "shipments.jsonl").open() as fh:
        docs = [json.loads(line) for line in fh]
    assert docs
    for doc in docs:
        assert doc["order_number"] in order_numbers
        assert doc["status"] == doc["events"][-1]["event_type"]


def test_pos_resends_are_exact_copies(generated):
    out, _ = generated
    for resend in (out / "s3" / "pos_sales").rglob("*_resend.csv"):
        original = resend.with_name(resend.name.replace("_resend", ""))
        assert original.read_bytes() == resend.read_bytes()


def test_sftp_trailers(generated):
    out, manifest = generated
    mismatched = 0
    for path in (out / "sftp").rglob("*.psv"):
        lines = path.read_text().splitlines()
        assert lines[0].startswith("H|RETAILPULSE|")
        details = [ln for ln in lines if ln.startswith("D|")][1:]  # first D row is the column names
        trailer = int(lines[-1].split("|")[1])
        mismatched += trailer != len(details)
    assert mismatched == manifest["counts"]["inventory_files_truncated"]


def test_supplier_feed_switches_to_v2(generated, small_cfg):
    out, _ = generated
    files = sorted((out / "sftp" / "suppliers" / "deliveries").glob("DLV_*.psv"))
    versions = [f.read_text().splitlines()[0].split("|")[-1] for f in files]
    cut = small_cfg.supplier_schema_v2_day
    assert set(versions[:cut]) == {"v1"}
    assert set(versions[cut:]) == {"v2"}
