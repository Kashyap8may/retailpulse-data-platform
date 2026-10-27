"""The data contracts in contracts/ must match what the generator writes."""

import csv
import json
from pathlib import Path

import yaml

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


def _contract(name):
    return yaml.safe_load((CONTRACTS / f"{name}.yaml").read_text())


def _names(columns):
    return [c["name"] for c in columns]


def _csv_header(path):
    with path.open(encoding="utf-8") as fh:
        return next(csv.reader(fh))


def _psv_header(path):
    return path.read_text().splitlines()[1].split("|")[1:]


def test_postgres_tables(generated):
    out, _ = generated
    for table, spec in _contract("postgres")["tables"].items():
        assert _csv_header(out / "postgres" / f"{table}.csv") == _names(spec["columns"]), table


def test_pos_sales(generated):
    out, _ = generated
    expected = _names(_contract("pos_sales")["columns"])
    for path in (out / "s3" / "pos_sales").rglob("*.csv"):
        assert _csv_header(path) == expected


def test_promotions(generated):
    out, _ = generated
    expected = set(_names(_contract("promotions")["columns"]))
    for path in (out / "s3" / "promotions").rglob("*.json"):
        for promo in json.loads(path.read_text())["promotions"]:
            assert set(promo) == expected


def test_carrier_api(generated):
    out, _ = generated
    expected = set(_names(_contract("carrier_api")["columns"]))
    with (out / "carrier_api" / "shipments.jsonl").open() as fh:
        for line in fh:
            assert set(json.loads(line)) == expected


def test_sftp_feeds(generated):
    out, _ = generated
    inventory = _names(_contract("sftp_3pl_inventory")["columns"])
    for path in (out / "sftp" / "3pl" / "inventory").glob("*.psv"):
        assert _psv_header(path) == inventory
    versions = _contract("sftp_supplier_deliveries")["versions"]
    for path in (out / "sftp" / "suppliers" / "deliveries").glob("*.psv"):
        version = path.read_text().splitlines()[0].split("|")[-1]
        assert _psv_header(path) == _names(versions[version]["columns"])
