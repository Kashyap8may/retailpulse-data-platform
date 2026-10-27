"""Source 2: the carrier tracking REST API (API Gateway + Lambda + DynamoDB).

Writes ``shipments.jsonl``: one JSON document per shipment with its tracking events, as the
API would return them at ``as_of``. Milestone 3 loads this file into DynamoDB, and the
Lambda serves it page by page with an ``updated_since`` filter.

Data problems carried over from real carrier feeds:
- EuroExpress sends event types in lower case.
- A small share of events are delivered twice with the same event_id.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..activity.simulation import SimulationResult
from ..rng import rng_for
from .common import json_default


def shipment_documents(sim: SimulationResult, as_of: datetime, seed: int, dq_rate: float):
    rng = rng_for(seed, "carrier-dq")
    for shp in sim.shipments:
        events = [e for e in shp["events"] if e["event_ts"] <= as_of]
        if not events:
            continue
        out_events = []
        for e in events:
            event = dict(e)
            if shp["carrier_code"] == "EUX":
                event["event_type"] = event["event_type"].lower()
            out_events.append(event)
            if rng.random() < dq_rate:
                out_events.append(dict(event))
        doc = {k: v for k, v in shp.items() if k != "events"}
        doc["status"] = out_events[-1]["event_type"]
        doc["created_at"] = events[0]["event_ts"]
        doc["updated_at"] = events[-1]["event_ts"]
        doc["events"] = out_events
        yield doc


def write_carrier_api(
    sim: SimulationResult, out_dir: Path, as_of: datetime, seed: int, dq_rate: float
) -> dict[str, int]:
    path = out_dir / "carrier_api" / "shipments.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for doc in shipment_documents(sim, as_of, seed, dq_rate):
            fh.write(json.dumps(doc, default=json_default) + "\n")
            n += 1
    return {"shipments": n}
