"""Replaying the daily folders in order must rebuild every source exactly as generate() shows it."""

import csv
import json
from datetime import timedelta

import pytest

from data_generator.daily import end_of, file_day, write_daily
from data_generator.simulate import generate
from data_generator.sources.postgres import LOAD_ORDER, TABLE_COLUMNS


@pytest.fixture(scope="session")
def daily(tmp_path_factory, small_cfg):
    out = tmp_path_factory.mktemp("daily")
    write_daily(small_cfg, out)
    return out


def _days_through(daily, through):
    return sorted(p for p in daily.iterdir() if p.is_dir() and p.name <= through.isoformat())


def _read_csv(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _checkpoints(cfg):
    return [cfg.start_date + timedelta(days=4), cfg.end_date]


def test_day_folders_span_the_opening_day_to_the_last_day(daily, small_cfg):
    names = sorted(p.name for p in daily.iterdir())
    assert names[0] == (small_cfg.start_date - timedelta(days=1)).isoformat()
    assert names[-1] == small_cfg.end_date.isoformat()


def test_postgres_upserts_rebuild_the_database(daily, small_cfg, tmp_path):
    for through in _checkpoints(small_cfg):
        rebuilt = {table: {} for table in LOAD_ORDER}
        for day in _days_through(daily, through):
            for table in LOAD_ORDER:
                path = day / "postgres" / f"{table}.csv"
                if path.exists():
                    key = TABLE_COLUMNS[table][0]
                    rebuilt[table].update({row[key]: row for row in _read_csv(path)})
        full = tmp_path / through.isoformat()
        generate(small_cfg, full, as_of=end_of(through))
        for table in LOAD_ORDER:
            key = TABLE_COLUMNS[table][0]
            expected = {row[key]: row for row in _read_csv(full / "postgres" / f"{table}.csv")}
            assert rebuilt[table] == expected, (through, table)


def test_shipment_puts_rebuild_the_api(daily, small_cfg, tmp_path):
    for through in _checkpoints(small_cfg):
        rebuilt = {}
        for day in _days_through(daily, through):
            path = day / "carrier_api" / "shipments.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    doc = json.loads(line)
                    rebuilt[doc["shipment_id"]] = doc
        full = tmp_path / through.isoformat()
        generate(small_cfg, full, as_of=end_of(through))
        lines = (full / "carrier_api" / "shipments.jsonl").read_text(encoding="utf-8").splitlines()
        assert rebuilt == {doc["shipment_id"]: doc for doc in map(json.loads, lines)}, through


def test_partner_files_arrive_on_their_day_unchanged(daily, small_cfg, tmp_path):
    full = tmp_path / "full"
    generate(small_cfg, full)
    expected = {}
    for path in full.rglob("*"):
        rel = path.relative_to(full).as_posix()
        if path.is_file() and rel.startswith(("s3/", "sftp/")) and file_day(rel) <= small_cfg.end_date:
            expected[rel] = path.read_bytes()
    published = {}
    for day in daily.iterdir():
        for path in day.rglob("*"):
            rel = path.relative_to(day).as_posix()
            if path.is_file() and rel.startswith(("s3/", "sftp/")):
                assert file_day(rel).isoformat() == day.name, rel
                published[rel] = path.read_bytes()
    assert published == expected
