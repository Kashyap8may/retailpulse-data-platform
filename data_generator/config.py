"""Settings that control how much data is generated and for which dates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    start_date: date = date(2026, 7, 1)
    days: int = 90

    n_customers: int = 50_000
    n_products: int = 1_200
    n_suppliers: int = 60
    n_promotions: int = 30

    online_orders_per_day: int = 1_500
    pos_txns_per_store_per_day: int = 120

    # Share of records that get a deliberate data-quality problem (duplicates, nulls, bad codes).
    dq_rate: float = 0.01
    # Day (counted from start_date) when suppliers switch to the v2 receipts file layout.
    supplier_schema_v2_day: int = 45

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.days - 1)

    def dates(self) -> list[date]:
        return [self.start_date + timedelta(days=i) for i in range(self.days)]

    def scaled(self, factor: float) -> GeneratorConfig:
        """Return a copy with volumes multiplied by ``factor`` (master data keeps sensible minimums)."""
        return replace(
            self,
            n_customers=max(200, int(self.n_customers * factor)),
            n_products=max(60, int(self.n_products * factor)),
            n_suppliers=max(6, int(self.n_suppliers * factor)),
            online_orders_per_day=max(20, int(self.online_orders_per_day * factor)),
            pos_txns_per_store_per_day=max(3, int(self.pos_txns_per_store_per_day * factor)),
        )
