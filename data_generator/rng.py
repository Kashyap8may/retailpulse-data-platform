"""Deterministic random number generators.

Every generator asks for its own ``random.Random`` keyed by the global seed plus a name
(and usually a date). The same seed therefore always produces the same data, and
regenerating a single day gives exactly the rows it had in a full run.
"""

from __future__ import annotations

import hashlib
import random


def rng_for(seed: int, *parts: object) -> random.Random:
    key = "|".join([str(seed), *map(str, parts)])
    digest = hashlib.sha256(key.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def weighted_choice(rng: random.Random, items: list, weights: list[float]):
    return rng.choices(items, weights=weights, k=1)[0]
