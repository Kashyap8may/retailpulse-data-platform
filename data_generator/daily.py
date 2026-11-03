"""Split one simulated year into what each source receives, day by day.

    python -m data_generator.daily --out output/daily              # 365 days from 2026-07-01
    python -m data_generator.daily --out output/daily --scale 0.05 --days 14

Writes one folder per UTC day. Day D holds what changed in the sources during D, as it looked
at the end of D (midnight UTC that night), so applying the days in order rebuilds each
source exactly as ``generate`` shows it. The first folder is the day before the simulation
starts and holds the opening state: master data and the customers who signed up earlier.

    <day>/postgres/<table>.csv          rows inserted or updated during the day (upsert by key)
    <day>/carrier_api/shipments.jsonl   shipments whose tracking changed (put by shipment_id)
    <day>/s3/...                        files that land in the S3 drop that day
    <day>/sftp/...                      files that arrive on the SFTP server that day

``data_generator.publish`` reads these folders from S3 and applies them to the live sources.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .activity.simulation import SimulationResult, simulate
from .config import GeneratorConfig
from .master import MasterData, build_master
from .sources.carrier_api import shipment_document
from .sources.common import json_default, public, write_csv
from .sources.pos_files import write_pos_files, write_promotion_exports
from .sources.postgres import TABLE_COLUMNS, row_as_of
from .sources.sftp_feeds import write_delivery_files, write_inventory_files

MASTER_TABLES = [
    "product_categories",
    "brands",
    "suppliers",
    "products",
    "stores",
    "warehouses",
    "loyalty_tiers",
]


def end_of(day: date) -> datetime:
    """The moment a day's changes are read: midnight UTC at the end of it."""
    return datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)


def day_of(ts: datetime) -> date:
    # A change exactly at midnight is already visible at end_of(previous day).
    return (ts - timedelta(microseconds=1)).astimezone(UTC).date()


def postgres_changes(cfg: GeneratorConfig, md: MasterData, sim: SimulationResult) -> dict[date, dict]:
    opening = cfg.start_date - timedelta(days=1)

    def bucket(ts: datetime) -> date:
        return max(day_of(ts), opening)

    days: dict[date, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    master = {
        "product_categories": md.categories,
        "brands": md.brands,
        "suppliers": [public(s) for s in md.suppliers],
        "products": [public(p) for p in md.products],
        "stores": md.stores,
        "warehouses": md.warehouses,
        "loyalty_tiers": md.loyalty_tiers,
    }
    for table in MASTER_TABLES:
        days[opening][table] = list(master[table])

    # Later versions overwrite earlier ones, in the same order postgres_tables reads them.
    latest: dict[date, dict[int, dict]] = defaultdict(dict)
    for version in sim.customer_versions:
        latest[bucket(max(version["created_at"], version["updated_at"]))][version["customer_id"]] = version
    for day, by_id in latest.items():
        days[day]["customers"] = [by_id[cid] for cid in sorted(by_id)]

    first_day = {}
    for table, records in [("orders", sim.orders), ("payments", sim.payments), ("returns", sim.returns)]:
        for rec in records:
            changed = sorted({bucket(ts) for ts, _status in rec["_events"]})
            if table == "orders":
                first_day[rec["order_id"]] = changed[0]
            for day in changed:
                days[day][table].append(row_as_of(rec, end_of(day)))
    for item in sim.order_items:
        days[first_day[item["order_id"]]]["order_items"].append(item)
    return days


def shipment_changes(cfg: GeneratorConfig, sim: SimulationResult) -> dict[date, list[dict]]:
    days: dict[date, list[dict]] = defaultdict(list)
    for shp in sim.shipments:
        for day in sorted({day_of(e["event_ts"]) for e in shp["events"]}):
            days[day].append(shipment_document(shp, end_of(day), cfg.seed, cfg.dq_rate))
    return days


# Which day a partner file arrives, read from its path.
_FILE_DAY = [
    re.compile(r"^s3/pos_sales/landing_date=(\d{4}-\d{2}-\d{2})/"),
    re.compile(r"^s3/promotions/export_date=(\d{4}-\d{2}-\d{2})/"),
    re.compile(r"^sftp/3pl/inventory/INV_[\w-]+_(\d{8})\.psv$"),
    re.compile(r"^sftp/suppliers/deliveries/DLV_(\d{8})\.psv$"),
]


def file_day(rel_path: str) -> date:
    for pattern in _FILE_DAY:
        match = pattern.match(rel_path)
        if match:
            text = match.group(1).replace("-", "")
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    raise ValueError(f"no arrival day for {rel_path}")


def write_daily(cfg: GeneratorConfig, out_dir: Path) -> dict[str, int]:
    md = build_master(cfg)
    sim = simulate(cfg, md)
    last_day = cfg.end_date
    counts: dict[str, int] = defaultdict(int)

    for day, tables in postgres_changes(cfg, md, sim).items():
        if day > last_day:
            continue
        for table, rows in tables.items():
            counts[f"postgres_{table}_rows"] += write_csv(
                out_dir / day.isoformat() / "postgres" / f"{table}.csv", TABLE_COLUMNS[table], rows
            )

    for day, docs in shipment_changes(cfg, sim).items():
        if day > last_day:
            continue
        path = out_dir / day.isoformat() / "carrier_api" / "shipments.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for doc in docs:
                fh.write(json.dumps(doc, default=json_default) + "\n")
        counts["shipment_documents"] += len(docs)

    # The file writers already name files by arrival day; move each into its day folder.
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        write_pos_files(cfg, sim, staging)
        write_promotion_exports(cfg, md, staging)
        write_inventory_files(cfg, sim, staging)
        write_delivery_files(cfg, sim, staging)
        for path in sorted(p for p in staging.rglob("*") if p.is_file()):
            rel = path.relative_to(staging).as_posix()
            day = file_day(rel)
            if day > last_day:
                continue
            target = out_dir / day.isoformat() / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, target)
            counts["files"] += 1

    counts["days"] = len([p for p in out_dir.iterdir() if p.is_dir()])
    return dict(counts)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Split the simulated year into daily source changes.")
    parser.add_argument("--out", type=Path, default=Path("output/daily"), help="output folder (replaced)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start-date", type=date.fromisoformat, default=GeneratorConfig.start_date)
    parser.add_argument("--days", type=int, default=GeneratorConfig.horizon_days)
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args(argv)

    cfg = GeneratorConfig(seed=args.seed, start_date=args.start_date, days=args.days)
    if args.scale != 1.0:
        cfg = cfg.scaled(args.scale)
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    started = time.perf_counter()
    counts = write_daily(cfg, args.out)
    print(f"Wrote {counts['days']} day folders into {args.out}/ in {time.perf_counter() - started:.0f}s")
    for name, n in sorted(counts.items()):
        print(f"  {name:<34} {n:>10,}")


if __name__ == "__main__":
    main()
