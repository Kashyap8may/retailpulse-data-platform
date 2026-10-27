"""Command line entry point: generate every source's data into a local folder.

    python -m data_generator.simulate --out output              # 90 days, full volume
    python -m data_generator.simulate --out output --scale 0.05 --days 14

The output folder mirrors the four source systems:

    output/postgres/      one CSV per table, as the database looks at --as-of
    output/carrier_api/   shipments.jsonl, as the API returns it at --as-of
    output/s3/            POS sales files by landing date, weekly promotions exports
    output/sftp/          3PL inventory files and supplier delivery files
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .activity.simulation import simulate
from .config import GeneratorConfig
from .master import build_master
from .sources.carrier_api import write_carrier_api
from .sources.pos_files import write_pos_files, write_promotion_exports
from .sources.postgres import write_postgres
from .sources.sftp_feeds import write_delivery_files, write_inventory_files


def generate(cfg: GeneratorConfig, out_dir: Path, as_of: datetime | None = None) -> dict:
    as_of = as_of or datetime.combine(cfg.end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    md = build_master(cfg)
    sim = simulate(cfg, md)
    counts = {}
    counts |= write_postgres(md, sim, out_dir, as_of)
    counts |= write_carrier_api(sim, out_dir, as_of, cfg.seed, cfg.dq_rate)
    counts |= write_pos_files(cfg, sim, out_dir)
    counts |= write_promotion_exports(cfg, md, out_dir)
    counts |= write_inventory_files(cfg, sim, out_dir)
    counts |= write_delivery_files(cfg, sim, out_dir)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "config": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in asdict(cfg).items()},
        "counts": counts,
    }
    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate RetailPulse source data.")
    parser.add_argument("--out", type=Path, default=Path("output"), help="output folder (replaced)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start-date", type=date.fromisoformat, default=GeneratorConfig.start_date)
    parser.add_argument("--days", type=int, default=GeneratorConfig.days)
    parser.add_argument(
        "--scale", type=float, default=1.0, help="multiply volumes, e.g. 0.05 for a quick run"
    )
    args = parser.parse_args(argv)

    cfg = GeneratorConfig(seed=args.seed, start_date=args.start_date, days=args.days)
    if args.scale != 1.0:
        cfg = cfg.scaled(args.scale)
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    started = time.perf_counter()
    manifest = generate(cfg, args.out)
    print(
        f"Generated {cfg.days} days ({cfg.start_date} to {cfg.end_date}) into {args.out}/ "
        f"in {time.perf_counter() - started:.0f}s"
    )
    for name, n in manifest["counts"].items():
        print(f"  {name:<28} {n:>10,}")


if __name__ == "__main__":
    main()
