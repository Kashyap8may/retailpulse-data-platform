"""Source 4: partner files on the SFTP server.

Two feeds, both pipe-delimited with a header (H) row, detail (D) rows and a trailer (T)
row holding the detail count, a common layout for B2B file exchange:

- ``3pl/inventory/INV_<warehouse>_<YYYYMMDD>.psv``: the third-party logistics provider's
  end-of-day stock per SKU and warehouse.
- ``suppliers/deliveries/DLV_<YYYYMMDD>.psv``: goods received against purchase orders,
  keyed by the supplier's own product code (vendor_sku), not our SKU.

Realistic problems:
- The delivery feed changes layout on ``supplier_schema_v2_day``: ``received_qty`` is
  renamed ``qty_received``, unit cost and currency are added, and the timestamp gains a
  UTC offset. The header row carries the layout version.
- About one inventory file in fifty is truncated: its trailer count does not match.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from ..activity.simulation import SimulationResult
from ..config import GeneratorConfig
from ..rng import rng_for
from .common import fmt

INVENTORY_COLUMNS = [
    "snapshot_date",
    "warehouse_id",
    "sku",
    "on_hand_qty",
    "on_order_qty",
    "last_receipt_date",
]
DELIVERY_COLUMNS_V1 = [
    "receipt_id",
    "po_number",
    "po_line_number",
    "supplier_id",
    "vendor_sku",
    "warehouse_id",
    "ordered_qty",
    "received_qty",
    "expected_date",
    "received_ts",
]
DELIVERY_COLUMNS_V2 = [
    "receipt_id",
    "po_number",
    "po_line_number",
    "supplier_id",
    "vendor_sku",
    "warehouse_id",
    "ordered_qty",
    "qty_received",
    "unit_cost",
    "cost_currency",
    "expected_date",
    "received_ts",
]


def _write_psv(
    path: Path,
    feed: str,
    file_date: date,
    version: str,
    columns: list[str],
    rows: list[list[str]],
    trailer_count: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"H|RETAILPULSE|{feed}|{file_date:%Y%m%d}|{version}", "|".join(["D", *columns])]
    lines += ["|".join(["D", *r]) for r in rows]
    lines.append(f"T|{len(rows) if trailer_count is None else trailer_count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inventory_files(cfg: GeneratorConfig, sim: SimulationResult, out_dir: Path) -> dict[str, int]:
    by_file: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for snap in sim.inventory_snapshots:
        by_file[(snap["warehouse_id"], snap["snapshot_date"])].append(snap)
    truncated = 0
    for (wh, d), snaps in sorted(by_file.items()):
        rows = [[fmt(s[c]) for c in INVENTORY_COLUMNS] for s in snaps]
        trailer = None
        if rng_for(cfg.seed, "inv-truncate", wh, d).random() < 0.02:
            trailer = len(rows)
            rows = rows[: int(len(rows) * 0.7)]
            truncated += 1
        path = out_dir / "sftp" / "3pl" / "inventory" / f"INV_{wh}_{d:%Y%m%d}.psv"
        _write_psv(path, "3PL-INVENTORY", d, "v1", INVENTORY_COLUMNS, rows, trailer)
    return {"inventory_files": len(by_file), "inventory_files_truncated": truncated}


def _delivery_row(rec: dict, columns: list[str], version: str) -> list[str]:
    values = dict(rec, qty_received=rec["received_qty"])
    if version == "v1":
        values["received_ts"] = rec["received_ts"].strftime("%Y-%m-%d %H:%M:%S")
    return [fmt(values[c]) for c in columns]


def write_delivery_files(cfg: GeneratorConfig, sim: SimulationResult, out_dir: Path) -> dict[str, int]:
    v2_from = cfg.start_date + timedelta(days=cfg.supplier_schema_v2_day)
    by_day: dict[date, list[dict]] = defaultdict(list)
    for rec in sim.deliveries:
        by_day[rec["received_ts"].date()].append(rec)
    rows_written = 0
    for d in cfg.dates():
        recs = sorted(by_day.get(d, []), key=lambda r: r["receipt_id"])
        version, columns = ("v2", DELIVERY_COLUMNS_V2) if d >= v2_from else ("v1", DELIVERY_COLUMNS_V1)
        rows = [_delivery_row(r, columns, version) for r in recs]
        path = out_dir / "sftp" / "suppliers" / "deliveries" / f"DLV_{d:%Y%m%d}.psv"
        _write_psv(path, "SUPPLIER-DELIVERIES", d, version, columns, rows)
        rows_written += len(rows)
    return {"delivery_files": cfg.days, "delivery_rows": rows_written}
