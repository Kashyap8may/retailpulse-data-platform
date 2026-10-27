"""Source 3: file drops in S3 (store POS sales and the marketing promotions calendar).

POS: every store uploads one CSV per business day, normally overnight. The files are
written under ``landing_date=YYYY-MM-DD`` (the day the file arrives in S3), which is what
Milestone 3 uploads each day. Realistic problems:
- About 3% of files arrive two or three days late.
- A few files are sent twice (``_resend`` suffix) with identical content.
- Timestamps are store-local with no time zone; the store master holds the zone.
- A small share of SKUs are lower case or unknown.

Promotions: marketing exports the full calendar of current and upcoming promotions every
Monday as JSON, so the same promotion appears in many exports and may change between them.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from ..activity.simulation import SimulationResult
from ..config import GeneratorConfig
from ..master import MasterData
from ..rng import rng_for
from .common import json_default, write_csv

POS_COLUMNS = [
    "transaction_id",
    "line_number",
    "business_date",
    "transaction_local_ts",
    "store_id",
    "register_id",
    "cashier_id",
    "sku",
    "quantity",
    "unit_price",
    "discount_amount",
    "line_amount",
    "currency",
    "tender_type",
    "loyalty_card_no",
    "promotion_id",
]


def pos_landing_date(cfg: GeneratorConfig, store_id: str, business_date: date) -> date:
    rng = rng_for(cfg.seed, "pos-landing", store_id, business_date)
    delay = 1 if rng.random() > 0.03 else rng.choice([2, 3])
    return business_date + timedelta(days=delay)


def write_pos_files(cfg: GeneratorConfig, sim: SimulationResult, out_dir: Path) -> dict[str, int]:
    by_file: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for line in sim.pos_lines:
        by_file[(line["store_id"], line["business_date"])].append(line)
    files = rows = 0
    for (store_id, business_date), lines in sorted(by_file.items()):
        landing = pos_landing_date(cfg, store_id, business_date)
        folder = out_dir / "s3" / "pos_sales" / f"landing_date={landing.isoformat()}"
        name = f"pos_{store_id}_{business_date:%Y%m%d}"
        rows += write_csv(folder / f"{name}.csv", POS_COLUMNS, lines)
        files += 1
        if rng_for(cfg.seed, "pos-resend", store_id, business_date).random() < cfg.dq_rate:
            write_csv(folder / f"{name}_resend.csv", POS_COLUMNS, lines)
            files += 1
    return {"pos_files": files, "pos_lines": rows}


def write_promotion_exports(cfg: GeneratorConfig, md: MasterData, out_dir: Path) -> dict[str, int]:
    campaigns = {c["campaign_id"]: c for c in md.campaigns}
    export_days = [d for d in cfg.dates() if d.weekday() == 0 or d == cfg.start_date]
    for export_date in export_days:
        rng = rng_for(cfg.seed, "promo-export", export_date)
        promos = []
        for p in md.promotions:
            if p["end_date"] < export_date - timedelta(days=7) or p["start_date"] > export_date + timedelta(
                days=28
            ):
                continue
            doc = {k: v for k, v in p.items() if k != "campaign_id"}
            doc["campaign"] = campaigns[p["campaign_id"]]
            # Marketing sometimes extends a promotion after it was first published.
            if p["start_date"] > export_date and rng.random() < 0.1:
                doc["end_date"] = p["end_date"] - timedelta(days=2)
            promos.append(doc)
        path = out_dir / "s3" / "promotions" / f"export_date={export_date.isoformat()}" / "promotions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": f"{export_date.isoformat()}T06:00:00Z",
            "source": "marketing-calendar",
            "promotions": promos,
        }
        path.write_text(json.dumps(payload, default=json_default, indent=2), encoding="utf-8")
    return {"promotion_exports": len(export_days)}
