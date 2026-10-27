"""Day-by-day simulation of the business: online orders, store sales, shipments, returns and supply.

The simulation runs one day at a time because the channels share state: online and store
sales draw down warehouse stock, low stock triggers purchase orders, late supplier
deliveries cause stock-outs, and customer spend moves customers up loyalty tiers.

Every record that changes over time keeps its full list of timestamped status events. The
source writers turn those into what each system would show "as of" a given moment, so the
same simulation can feed a one-off history load and a day-by-day incremental feed.
"""

from __future__ import annotations

import bisect
import itertools
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import GeneratorConfig
from ..master import MasterData
from ..reference import (
    CARRIERS,
    CITIES,
    COUNTRIES,
    LOYALTY_TIERS,
    PAYMENT_METHODS,
    POS_TENDER_TYPES,
    RETURN_RATE_BY_DEPARTMENT,
    RETURN_REASONS,
    SERVICE_LEVELS,
    WAREHOUSES,
)
from ..rng import rng_for

TAX_RATE = {"US": 0.0725, "GB": 0.20, "DE": 0.19}
CITY_INFO = {c[0]: c for c in CITIES}
STORE_TYPE_TRAFFIC = {"FLAGSHIP": 2.2, "STANDARD": 1.0, "OUTLET": 0.8}
LINE_COUNT_WEIGHTS = [0.55, 0.25, 0.13, 0.07]
# Rough USD conversion used only inside the simulation (spend thresholds). Real FX comes from the FX API.
USD_PER_UNIT = {"USD": 1.0, "GBP": 1.27, "EUR": 1.08}


@dataclass
class SimulationResult:
    orders: list[dict] = field(default_factory=list)
    order_items: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    returns: list[dict] = field(default_factory=list)
    shipments: list[dict] = field(default_factory=list)
    pos_lines: list[dict] = field(default_factory=list)
    inventory_snapshots: list[dict] = field(default_factory=list)
    deliveries: list[dict] = field(default_factory=list)
    customer_versions: list[dict] = field(default_factory=list)


def local_price(list_price_usd: float, country: str) -> float:
    """Country price list: the USD price times a factor, rounded to a .99 price point."""
    factor = COUNTRIES[country][3]
    return max(math.floor(list_price_usd * factor), 1) - 0.01


def status_as_of(events: list[tuple[datetime, str]], as_of: datetime) -> tuple[str, datetime] | None:
    """The last (status, timestamp) at or before ``as_of``; None if the record did not exist yet."""
    seen = None
    for ts, status in events:
        if ts <= as_of:
            seen = (status, ts)
        else:
            break
    return seen


def _warehouse_for(country: str, region: str) -> str:
    for wh_id, (_n, _c, wh_country, regions) in WAREHOUSES.items():
        if wh_country == country and (regions is None or region in regions):
            return wh_id
    raise ValueError(f"no warehouse for {country}/{region}")


class Simulator:
    def __init__(self, cfg: GeneratorConfig, md: MasterData):
        self.cfg = cfg
        self.md = md
        self.out = SimulationResult()
        self.products = md.products
        pop = [p["_popularity"] for p in self.products]
        self.product_cum = list(itertools.accumulate(pop))
        self.pop_share = {p["product_id"]: p["_popularity"] / self.product_cum[-1] for p in self.products}

        self.customers = md.customers
        self.customer_cum = list(itertools.accumulate(c["_activity"] for c in self.customers))
        self.card_holders = defaultdict(list)
        for c in self.customers:
            if c["loyalty_card_no"]:
                self.card_holders[c["country_code"]].append(c)
        self.lifetime_spend = defaultdict(
            float, {c["customer_id"]: c["_prior_spend"] for c in self.customers}
        )

        self.order_seq = itertools.count(9_000_001)
        self.item_seq = itertools.count(1)
        self.payment_seq = itertools.count(1)
        self.return_seq = itertools.count(1)
        self.po_seq = itertools.count(1)
        self.receipt_seq = itertools.count(1)

        self._init_inventory()

    # ------------------------------------------------------------------ inventory
    def _expected_daily_units(self) -> float:
        cfg = self.cfg
        online = cfg.online_orders_per_day * 1.75 * 1.3
        stores = sum(STORE_TYPE_TRAFFIC[s["store_type"]] for s in self.md.stores)
        pos = cfg.pos_txns_per_store_per_day * stores * 2.0 * 1.3
        return online + pos

    def _init_inventory(self) -> None:
        wh_share = {"WH-US-E": 0.45, "WH-US-W": 0.17, "WH-GB": 0.22, "WH-DE": 0.16}
        total = self._expected_daily_units()
        rng = rng_for(self.cfg.seed, "inventory-init")
        self.stock: dict[tuple[str, int], int] = {}
        self.demand_ema: dict[tuple[str, int], float] = {}
        self.on_order: dict[tuple[str, int], int] = defaultdict(int)
        self.last_receipt: dict[tuple[str, int], date] = {}
        for wh in WAREHOUSES:
            for p in self.products:
                expected = total * self.pop_share[p["product_id"]] * wh_share[wh]
                key = (wh, p["product_id"])
                self.demand_ema[key] = expected
                self.stock[key] = int(expected * rng.uniform(4, 24)) + rng.randint(0, 3)
        self.arrivals: dict[date, list[dict]] = defaultdict(list)
        self.restocks: dict[date, list[tuple[str, int, int]]] = defaultdict(list)
        self.units_today: dict[tuple[str, int], int] = defaultdict(int)

    def _take_stock(self, wh: str, product_id: int, qty: int) -> bool:
        key = (wh, product_id)
        if self.stock[key] < qty:
            return False
        self.stock[key] -= qty
        self.units_today[key] += qty
        return True

    # ------------------------------------------------------------------ helpers
    def _pick_product(self, rng) -> dict:
        x = rng.random() * self.product_cum[-1]
        return self.products[bisect.bisect_left(self.product_cum, x)]

    def _pick_customer(self, rng, before: datetime) -> dict | None:
        for _ in range(20):
            x = rng.random() * self.customer_cum[-1]
            c = self.customers[bisect.bisect_left(self.customer_cum, x)]
            if c["created_at"] <= before:
                return c
        return None

    def _promotion(self, d: date, channel: str, country: str, product: dict) -> dict | None:
        cat_id = self.md.category_of(product)["category_id"]
        best = None
        for promo in self.md.promotions:
            if not (promo["start_date"] <= d <= promo["end_date"]):
                continue
            if promo["channel"] not in ("ALL", channel) or country not in promo["country_codes"]:
                continue
            if promo["category_id"] not in (None, cat_id):
                continue
            if best is None or promo["discount_pct"] > best["discount_pct"]:
                best = promo
        return best

    def _add_spend(self, customer: dict, amount_usd: float, ts: datetime) -> None:
        cid = customer["customer_id"]
        self.lifetime_spend[cid] += amount_usd
        new_tier = customer["loyalty_tier"]
        for code, _name, threshold, _pct in LOYALTY_TIERS:
            if self.lifetime_spend[cid] >= threshold:
                new_tier = code
        if new_tier != customer["loyalty_tier"]:
            customer["loyalty_tier"] = new_tier
            customer["updated_at"] = ts + timedelta(minutes=1)
            self._snapshot_customer(customer)

    def _snapshot_customer(self, customer: dict) -> None:
        self.out.customer_versions.append({k: v for k, v in customer.items() if not k.startswith("_")})

    @staticmethod
    def _day_factor(d: date, weekend_lift: float) -> float:
        return weekend_lift if d.weekday() >= 5 else 1.0

    # ------------------------------------------------------------------ run
    def run(self) -> SimulationResult:
        # Customers as they were when the simulation starts.
        for c in self.customers:
            self._snapshot_customer(c)
        for d in self.cfg.dates():
            self.units_today.clear()
            self._receive_arrivals(d)
            self._customer_moves(d)
            self._online_day(d)
            self._store_day(d)
            self._end_of_day_supply(d)
        return self.out

    def _customer_moves(self, d: date) -> None:
        rng = rng_for(self.cfg.seed, "moves", d)
        for c in self.customers:
            if c.get("_move_on") == d:
                cities = [x for x in CITIES if x[2] == c["country_code"] and x[0] != c["city"]]
                c["city"] = rng.choice(cities)[0]
                c["address_line1"] = (
                    f"{rng.randint(1, 400)} {rng.choice(['High', 'Park', 'Station', 'Main'])} Street"
                )
                c["postal_code"] = f"{rng.randint(10000, 99999)}"
                c["updated_at"] = datetime.combine(d, time(rng.randint(7, 22)), tzinfo=UTC)
                self._snapshot_customer(c)

    # ------------------------------------------------------------------ online
    def _online_day(self, d: date) -> None:
        cfg = self.cfg
        rng = rng_for(cfg.seed, "online", d)
        trend = 1 + 0.15 * (d - cfg.start_date).days / max(cfg.days, 1)
        n_orders = int(cfg.online_orders_per_day * self._day_factor(d, 1.2) * trend * rng.uniform(0.85, 1.15))
        for _ in range(n_orders):
            day_start = datetime.combine(d, time(0), tzinfo=UTC)
            customer = self._pick_customer(rng, day_start + timedelta(hours=23))
            if customer is None:
                continue
            self._online_order(d, rng, customer)

    def _online_order(self, d: date, rng, customer: dict) -> None:
        country = customer["country_code"]
        city = CITY_INFO[customer["city"]]
        tz = ZoneInfo(city[3])
        local_hour = rng.choices(
            range(24), weights=[1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 7, 7, 6, 6, 6, 7, 8, 9, 10, 9, 6, 3]
        )[0]
        local_ts = datetime.combine(d, time(local_hour, rng.randint(0, 59), rng.randint(0, 59)), tzinfo=tz)
        order_ts = local_ts.astimezone(UTC)
        if order_ts < customer["created_at"]:
            order_ts = customer["created_at"] + timedelta(minutes=rng.randint(2, 50))
        wh = _warehouse_for(country, city[1])
        currency = COUNTRIES[country][1]

        lines = []
        for _ in range(rng.choices([1, 2, 3, 4], LINE_COUNT_WEIGHTS)[0]):
            product = self._pick_product(rng)
            qty = rng.choices([1, 2, 3], [0.8, 0.15, 0.05])[0]
            if any(line["product"] is product for line in lines):
                continue
            lines.append({"product": product, "qty": qty})

        cancel_roll = rng.random()
        cancelled = cancel_roll < 0.04
        kept = []
        for line in lines:
            if cancelled or self._take_stock(wh, line["product"]["product_id"], line["qty"]):
                kept.append(line)
        if not kept:
            return  # everything was out of stock: the customer leaves without ordering

        order_id = next(self.order_seq)
        service = rng.choices(list(SERVICE_LEVELS), [v[1] for v in SERVICE_LEVELS.values()])[0]
        subtotal = discount_total = 0.0
        items = []
        for line_no, line in enumerate(kept, start=1):
            product = line["product"]
            price = local_price(product["list_price_usd"], country)
            promo = self._promotion(d, "ONLINE", country, product)
            gross = round(price * line["qty"], 2)
            discount = round(gross * promo["discount_pct"] / 100, 2) if promo else 0.0
            subtotal += gross
            discount_total += discount
            items.append(
                {
                    "order_item_id": next(self.item_seq),
                    "order_id": order_id,
                    "line_number": line_no,
                    "product_id": product["product_id"],
                    "quantity": line["qty"],
                    "unit_price": price,
                    "discount_amount": discount,
                    "promotion_id": promo["promotion_id"] if promo else None,
                    "created_at": order_ts,
                    "updated_at": order_ts,
                }
            )
        shipping_fee = round(SERVICE_LEVELS[service][2] / USD_PER_UNIT[currency], 2)
        if subtotal - discount_total > 75 / USD_PER_UNIT[currency] and service == "STANDARD":
            shipping_fee = 0.0
        tax = round((subtotal - discount_total + shipping_fee) * TAX_RATE[country], 2)
        total = round(subtotal - discount_total + shipping_fee + tax, 2)

        events = [(order_ts, "PLACED")]
        payment_method = rng.choices(*zip(*PAYMENT_METHODS[country], strict=True))[0]
        payment = {
            "payment_id": next(self.payment_seq),
            "order_id": order_id,
            "payment_method": payment_method,
            "payment_type": "CHARGE",
            "amount": total,
            "currency": currency,
            "provider_reference": f"pay_{rng.getrandbits(48):012x}",
            "_events": [(order_ts + timedelta(seconds=rng.randint(2, 40)), "AUTHORIZED")],
        }
        order = {
            "order_id": order_id,
            "order_number": f"RPO-{order_id}",
            "customer_id": customer["customer_id"],
            "order_ts": order_ts,
            "channel": rng.choices(["WEB", "APP"], [0.6, 0.4])[0],
            "currency": currency,
            "shipping_service": service,
            "ship_to_city": customer["city"],
            "ship_to_postal_code": customer["postal_code"],
            "ship_to_country": country,
            "fulfilment_warehouse_id": wh,
            "subtotal_amount": round(subtotal, 2),
            "discount_amount": round(discount_total, 2),
            "shipping_amount": shipping_fee,
            "tax_amount": tax,
            "total_amount": total,
            "_events": events,
        }
        self.out.orders.append(order)
        self.out.order_items.extend(items)
        self.out.payments.append(payment)

        if cancelled:
            reason_ts = order_ts + timedelta(minutes=rng.randint(1, 90))
            if cancel_roll < 0.015:
                payment["_events"].append((reason_ts, "FAILED"))
                events.append((reason_ts, "PAYMENT_FAILED"))
            else:
                payment["_events"].append((reason_ts, "VOIDED"))
                events.append((reason_ts, "CANCELLED"))
            return

        paid_ts = order_ts + timedelta(minutes=rng.randint(1, 15))
        events.append((paid_ts, "PAID"))
        self._add_spend(customer, total * USD_PER_UNIT[currency], paid_ts)
        self._ship(order, items, payment, rng, country, service, wh)

    def _ship(self, order: dict, items: list[dict], payment: dict, rng, country: str, service: str, wh: str):
        events = order["_events"]
        paid_ts = events[-1][0]
        ship_ts = paid_ts + timedelta(hours=rng.uniform(3, 40))
        carriers = [cid for cid, (_n, countries, _ot) in CARRIERS.items() if country in countries]
        carrier = rng.choice(carriers)
        carrier_name, _countries, on_time = CARRIERS[carrier]
        promised = ship_ts.date() + timedelta(days=SERVICE_LEVELS[service][0])
        payment["_events"].append((ship_ts, "CAPTURED"))
        events.append((ship_ts, "SHIPPED"))

        if rng.random() < on_time:
            deliver_date = ship_ts.date() + timedelta(days=rng.randint(1, SERVICE_LEVELS[service][0]))
        else:
            deliver_date = promised + timedelta(
                days=rng.choices([1, 2, 3, 5, 8], [0.4, 0.25, 0.15, 0.12, 0.08])[0]
            )
        city_tz = ZoneInfo(CITY_INFO[order["ship_to_city"]][3])
        deliver_ts = datetime.combine(
            deliver_date, time(rng.randint(9, 19), rng.randint(0, 59)), tzinfo=city_tz
        ).astimezone(UTC)
        lost = rng.random() < 0.012

        wh_city = WAREHOUSES[wh][1]
        track = [
            ("LABEL_CREATED", ship_ts - timedelta(hours=rng.uniform(0.5, 3)), wh_city),
            ("PICKED_UP", ship_ts, wh_city),
        ]
        hops = rng.randint(1, 3)
        for h in range(1, hops + 1):
            hop_ts = ship_ts + (deliver_ts - ship_ts) * h / (hops + 1.5)
            track.append(("IN_TRANSIT", hop_ts, f"{carrier_name} hub {rng.randint(1, 40):02d}"))
        if lost:
            fail_ts = deliver_ts
            track.append(
                ("OUT_FOR_DELIVERY", fail_ts - timedelta(hours=rng.uniform(2, 6)), order["ship_to_city"])
            )
            track.append(("DELIVERY_FAILED", fail_ts, order["ship_to_city"]))
            track.append(("RETURNED_TO_SENDER", fail_ts + timedelta(days=rng.randint(3, 6)), wh_city))
            events.append((fail_ts, "DELIVERY_FAILED"))
        else:
            if rng.random() < 0.05:  # one failed attempt, delivered next day
                track.append(
                    ("OUT_FOR_DELIVERY", deliver_ts - timedelta(days=1, hours=3), order["ship_to_city"])
                )
                track.append(("DELIVERY_ATTEMPTED", deliver_ts - timedelta(days=1), order["ship_to_city"]))
            track.append(
                ("OUT_FOR_DELIVERY", deliver_ts - timedelta(hours=rng.uniform(1, 5)), order["ship_to_city"])
            )
            track.append(("DELIVERED", deliver_ts, order["ship_to_city"]))
            events.append((deliver_ts, "DELIVERED"))

        tracking_events = []
        for n, (etype, ts, location) in enumerate(sorted(track, key=lambda t: t[1]), start=1):
            tracking_events.append(
                {
                    "event_id": f"{order['order_id']}-{n}",
                    "event_type": etype,
                    "event_ts": ts,
                    "location": location,
                }
            )
        self.out.shipments.append(
            {
                "shipment_id": f"SHP{order['order_id']}",
                "order_number": order["order_number"],
                "carrier_code": carrier,
                "carrier_name": carrier_name,
                "service_level": service,
                "tracking_number": f"{carrier}{rng.getrandbits(40):012d}",
                "origin_warehouse_id": wh,
                "destination_city": order["ship_to_city"],
                "destination_postal_code": order["ship_to_postal_code"],
                "destination_country": order["ship_to_country"],
                "promised_delivery_date": promised,
                "events": tracking_events,
            }
        )
        if not lost:
            self._maybe_return(order, items, payment, rng, deliver_ts, wh)

    def _maybe_return(self, order, items, payment, rng, deliver_ts, wh) -> None:
        returned_lines = 0
        refund_total = 0.0
        last_ts = deliver_ts
        for item in items:
            product = self.md.product_by_id[item["product_id"]]
            rate = RETURN_RATE_BY_DEPARTMENT[self.md.department_of(product)]
            if rng.random() >= rate:
                continue
            requested = deliver_ts + timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 12))
            received = requested + timedelta(days=rng.randint(3, 9))
            refunded = received + timedelta(hours=rng.randint(4, 72))
            qty = item["quantity"] if item["quantity"] == 1 or rng.random() < 0.7 else 1
            refund = round(
                (item["unit_price"] * qty - item["discount_amount"] * qty / item["quantity"])
                * (1 + TAX_RATE[order["ship_to_country"]]),
                2,
            )
            self.out.returns.append(
                {
                    "return_id": next(self.return_seq),
                    "order_id": order["order_id"],
                    "order_item_id": item["order_item_id"],
                    "quantity": qty,
                    "reason_code": rng.choices(*zip(*RETURN_REASONS, strict=True))[0],
                    "refund_amount": refund,
                    "currency": order["currency"],
                    "_events": [(requested, "REQUESTED"), (received, "RECEIVED"), (refunded, "REFUNDED")],
                }
            )
            self.restocks[received.date()].append((wh, item["product_id"], qty))
            returned_lines += 1
            refund_total += refund
            last_ts = max(last_ts, refunded)
        if returned_lines:
            status = "RETURNED" if returned_lines == len(items) else "PARTIALLY_RETURNED"
            order["_events"].append((last_ts, status))
            self.out.payments.append(
                {
                    "payment_id": next(self.payment_seq),
                    "order_id": order["order_id"],
                    "payment_method": payment["payment_method"],
                    "payment_type": "REFUND",
                    "amount": -round(refund_total, 2),
                    "currency": order["currency"],
                    "provider_reference": f"ref_{rng.getrandbits(48):012x}",
                    "_events": [(last_ts, "COMPLETED")],
                }
            )

    # ------------------------------------------------------------------ stores
    def _store_day(self, d: date) -> None:
        cfg = self.cfg
        for store in self.md.stores:
            rng = rng_for(cfg.seed, "pos", store["store_id"], d)
            tz = ZoneInfo(store["timezone"])
            wh = _warehouse_for(store["country_code"], store["region"])
            currency = COUNTRIES[store["country_code"]][1]
            n = int(
                cfg.pos_txns_per_store_per_day
                * STORE_TYPE_TRAFFIC[store["store_type"]]
                * self._day_factor(d, 1.45)
                * rng.uniform(0.8, 1.2)
            )
            if store["country_code"] == "DE" and d.weekday() == 6:
                n = 0  # German shops are closed on Sundays
            for t in range(1, n + 1):
                local_ts = datetime.combine(
                    d, time(rng.randint(9, 20), rng.randint(0, 59), rng.randint(0, 59))
                )
                holders = self.card_holders[store["country_code"]]
                customer = rng.choice(holders) if holders and rng.random() < 0.4 else None
                txn_id = f"{store['store_id']}-{d:%Y%m%d}-{t:04d}"
                register = f"R{rng.randint(1, 6 if store['store_type'] != 'FLAGSHIP' else 14):02d}"
                tender = rng.choices(*zip(*POS_TENDER_TYPES, strict=True))[0]
                cashier = f"{store['store_id']}-E{rng.randint(1, 25):03d}"
                spend = 0.0
                for line_no in range(1, rng.choices([1, 2, 3, 4, 5], [0.45, 0.25, 0.15, 0.1, 0.05])[0] + 1):
                    product = self._pick_product(rng)
                    qty = rng.choices([1, 2, 3], [0.82, 0.14, 0.04])[0]
                    is_return = rng.random() < 0.03
                    if is_return:
                        qty = -qty
                        self.restocks[d + timedelta(days=1)].append((wh, product["product_id"], -qty))
                    elif not self._take_stock(wh, product["product_id"], qty):
                        continue
                    price = local_price(product["list_price_usd"], store["country_code"])
                    promo = None if is_return else self._promotion(d, "STORE", store["country_code"], product)
                    discount = round(price * qty * promo["discount_pct"] / 100, 2) if promo else 0.0
                    line_total = round(price * qty - discount, 2)
                    spend += line_total
                    sku = product["sku"]
                    if rng.random() < cfg.dq_rate / 3:
                        sku = sku.lower() if rng.random() < 0.5 else f"RP-{rng.randint(990000, 999999)}"
                    self.out.pos_lines.append(
                        {
                            "transaction_id": txn_id,
                            "line_number": line_no,
                            "business_date": d,
                            "transaction_local_ts": local_ts,
                            "store_id": store["store_id"],
                            "register_id": register,
                            "cashier_id": cashier,
                            "sku": sku,
                            "quantity": qty,
                            "unit_price": price,
                            "discount_amount": discount,
                            "line_amount": line_total,
                            "currency": currency,
                            "tender_type": tender,
                            "loyalty_card_no": customer["loyalty_card_no"] if customer else None,
                            "promotion_id": promo["promotion_id"] if promo else None,
                        }
                    )
                if customer and spend > 0:
                    utc_ts = local_ts.replace(tzinfo=tz).astimezone(UTC)
                    self._add_spend(customer, spend * USD_PER_UNIT[currency], utc_ts)

    # ------------------------------------------------------------------ supply
    def _receive_arrivals(self, d: date) -> None:
        for wh, product_id, qty in self.restocks.pop(d, []):
            self.stock[(wh, product_id)] += qty
        for receipt in self.arrivals.pop(d, []):
            key = (receipt["warehouse_id"], receipt["product_id"])
            self.stock[key] += receipt["received_qty"]
            self.on_order[key] -= receipt["ordered_qty"]
            self.last_receipt[key] = d
            self.out.deliveries.append(receipt)

    def _end_of_day_supply(self, d: date) -> None:
        rng = rng_for(self.cfg.seed, "supply", d)
        new_pos: dict[tuple[str, str], str] = {}
        line_counter: dict[str, int] = defaultdict(int)
        for wh in WAREHOUSES:
            for p in self.products:
                key = (wh, p["product_id"])
                self.demand_ema[key] = 0.85 * self.demand_ema[key] + 0.15 * self.units_today.get(key, 0)
                supplier = self.md.supplier_by_id[p["supplier_id"]]
                cover_days = supplier["lead_time_days"] + 3
                reorder_point = self.demand_ema[key] * cover_days
                if self.stock[key] + self.on_order[key] <= reorder_point and self.demand_ema[key] > 0.05:
                    qty = max(12, math.ceil(self.demand_ema[key] * (cover_days + 14) / 12) * 12)
                    po_key = (supplier["supplier_id"], wh)
                    if po_key not in new_pos:
                        new_pos[po_key] = f"PO-{d.year}-{next(self.po_seq):06d}"
                    po_number = new_pos[po_key]
                    line_counter[po_number] += 1
                    self.on_order[key] += qty
                    self._schedule_delivery(d, rng, supplier, p, wh, po_number, line_counter[po_number], qty)
                self.out.inventory_snapshots.append(
                    {
                        "snapshot_date": d,
                        "warehouse_id": wh,
                        "sku": p["sku"],
                        "on_hand_qty": self.stock[key],
                        "on_order_qty": self.on_order[key],
                        "last_receipt_date": self.last_receipt.get(key),
                    }
                )

    def _schedule_delivery(self, d, rng, supplier, product, wh, po_number, line_no, qty) -> None:
        expected = d + timedelta(days=supplier["lead_time_days"])
        if rng.random() < supplier["_on_time_rate"]:
            arrival = expected - timedelta(days=rng.choice([0, 0, 0, 1]))
        else:
            arrival = expected + timedelta(
                days=rng.choices([1, 2, 4, 7, 12], [0.35, 0.25, 0.2, 0.12, 0.08])[0]
            )
        received = qty if rng.random() < supplier["_fill_rate"] else int(qty * rng.uniform(0.6, 0.95))
        receipt_ts = datetime.combine(arrival, time(rng.randint(6, 17), rng.randint(0, 59)), tzinfo=UTC)
        self.arrivals[arrival].append(
            {
                "receipt_id": f"RCV{next(self.receipt_seq):07d}",
                "po_number": po_number,
                "po_line_number": line_no,
                "po_date": d,
                "supplier_id": supplier["supplier_id"],
                "vendor_sku": product["vendor_sku"],
                "product_id": product["product_id"],
                "warehouse_id": wh,
                "ordered_qty": qty,
                "received_qty": received,
                "unit_cost": round(product["unit_cost_usd"], 2),
                "cost_currency": "USD",
                "expected_date": expected,
                "received_ts": receipt_ts,
            }
        )


def simulate(cfg: GeneratorConfig, md: MasterData) -> SimulationResult:
    return Simulator(cfg, md).run()
