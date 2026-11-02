"""Master data shared by every source: categories, brands, suppliers, products, stores, customers, promotions.

All sources draw their keys from the same master data, the way systems in a real company
share a product catalogue and a customer base. Where real systems disagree (the supplier
uses its own product codes, the POS knows customers only by loyalty card number), the
generators reproduce that too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from faker import Faker

from .config import GeneratorConfig
from .reference import (
    CITIES,
    COUNTRIES,
    DEPARTMENT_SALES_WEIGHT,
    LOYALTY_TIERS,
    PRODUCT_HIERARCHY,
    STORES_PER_COUNTRY,
    WAREHOUSES,
)
from .rng import rng_for

SUPPLIER_COUNTRIES = [
    ("CN", 0.35),
    ("VN", 0.12),
    ("US", 0.15),
    ("DE", 0.10),
    ("GB", 0.08),
    ("IT", 0.08),
    ("PT", 0.06),
    ("TR", 0.06),
]
BRAND_SYLLABLES = [
    "nor",
    "vel",
    "ka",
    "lum",
    "ori",
    "tes",
    "bra",
    "zen",
    "mar",
    "qui",
    "sol",
    "dex",
    "fin",
    "ar",
    "co",
    "ly",
    "tro",
    "vio",
    "pax",
    "ru",
]
EMAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "web.de"]
PRODUCT_ADJECTIVES = [
    "Classic",
    "Essential",
    "Premium",
    "Compact",
    "Eco",
    "Pro",
    "Everyday",
    "Urban",
    "Nordic",
    "Studio",
    "Ultra",
    "Soft",
    "Smart",
    "Heritage",
    "Active",
]


@dataclass
class MasterData:
    categories: list[dict] = field(default_factory=list)
    brands: list[dict] = field(default_factory=list)
    suppliers: list[dict] = field(default_factory=list)
    products: list[dict] = field(default_factory=list)
    stores: list[dict] = field(default_factory=list)
    warehouses: list[dict] = field(default_factory=list)
    customers: list[dict] = field(default_factory=list)
    loyalty_tiers: list[dict] = field(default_factory=list)
    campaigns: list[dict] = field(default_factory=list)
    promotions: list[dict] = field(default_factory=list)

    # Lookups built after generation (not written to any source).
    product_by_id: dict[int, dict] = field(default_factory=dict)
    category_by_id: dict[int, dict] = field(default_factory=dict)
    supplier_by_id: dict[str, dict] = field(default_factory=dict)
    customer_by_id: dict[int, dict] = field(default_factory=dict)

    def index(self) -> None:
        self.product_by_id = {p["product_id"]: p for p in self.products}
        self.category_by_id = {c["category_id"]: c for c in self.categories}
        self.supplier_by_id = {s["supplier_id"]: s for s in self.suppliers}
        self.customer_by_id = {c["customer_id"]: c for c in self.customers}

    def department_of(self, product: dict) -> str:
        sub = self.category_by_id[product["category_id"]]
        cat = self.category_by_id[sub["parent_category_id"]]
        return self.category_by_id[cat["parent_category_id"]]["category_name"]

    def category_of(self, product: dict) -> dict:
        """The level-2 category (e.g. Kitchen) that a product's subcategory belongs to."""
        return self.category_by_id[self.category_by_id[product["category_id"]]["parent_category_id"]]


def _ts(d: date, rng, start_hour: int = 0, end_hour: int = 24) -> datetime:
    seconds = rng.randint(start_hour * 3600, end_hour * 3600 - 1)
    return datetime.combine(d, time(0), tzinfo=UTC) + timedelta(seconds=seconds)


def build_master(cfg: GeneratorConfig) -> MasterData:
    md = MasterData()
    created = datetime(2023, 1, 1, tzinfo=UTC)
    _build_categories(md, created)
    _build_brands(md, cfg, created)
    _build_suppliers(md, cfg, created)
    _build_products(md, cfg, created)
    _build_locations(md, cfg, created)
    md.loyalty_tiers = [
        {"tier_code": code, "tier_name": name, "min_lifetime_spend_usd": spend, "discount_pct": pct}
        for code, name, spend, pct in LOYALTY_TIERS
    ]
    _build_customers(md, cfg)
    _build_promotions(md, cfg)
    md.index()
    return md


def _build_categories(md: MasterData, created: datetime) -> None:
    next_id = 1
    for dept, cats in PRODUCT_HIERARCHY.items():
        dept_id = next_id
        next_id += 1
        md.categories.append(_category(dept_id, None, dept, "DEPARTMENT", created))
        for cat, (subs, *_rest) in cats.items():
            cat_id = next_id
            next_id += 1
            md.categories.append(_category(cat_id, dept_id, cat, "CATEGORY", created))
            for sub in subs:
                md.categories.append(_category(next_id, cat_id, sub, "SUBCATEGORY", created))
                next_id += 1


def _category(cid: int, parent: int | None, name: str, level: str, created: datetime) -> dict:
    return {
        "category_id": cid,
        "parent_category_id": parent,
        "category_name": name,
        "category_level": level,
        "created_at": created,
        "updated_at": created,
    }


def _build_brands(md: MasterData, cfg: GeneratorConfig, created: datetime) -> None:
    rng = rng_for(cfg.seed, "brands")
    names: set[str] = set()
    for dept in PRODUCT_HIERARCHY:
        for _ in range(12):
            while True:
                name = "".join(rng.sample(BRAND_SYLLABLES, rng.choice([2, 3]))).capitalize()
                if name not in names:
                    break
            names.add(name)
            md.brands.append(
                {
                    "brand_id": len(md.brands) + 1,
                    "brand_name": name,
                    "primary_department": dept,
                    "created_at": created,
                    "updated_at": created,
                }
            )


def _build_suppliers(md: MasterData, cfg: GeneratorConfig, created: datetime) -> None:
    rng = rng_for(cfg.seed, "suppliers")
    fake = Faker("en_US")
    fake.seed_instance(cfg.seed)
    codes, weights = zip(*SUPPLIER_COUNTRIES, strict=True)
    for i in range(1, cfg.n_suppliers + 1):
        name = fake.unique.company()
        domain = "".join(ch for ch in name.lower() if ch.isalnum())[:18]
        md.suppliers.append(
            {
                "supplier_id": f"SUP{i:03d}",
                "supplier_name": name,
                "country_code": rng.choices(codes, weights)[0],
                "lead_time_days": rng.randint(5, 30),
                "contact_email": f"orders@{domain}.example.com",
                # Hidden behaviour used by the simulation, not exported.
                "_on_time_rate": round(rng.uniform(0.6, 0.97), 3),
                "_fill_rate": round(rng.uniform(0.85, 1.0), 3),
                "created_at": created,
                "updated_at": created,
            }
        )


def _build_products(md: MasterData, cfg: GeneratorConfig, created: datetime) -> None:
    rng = rng_for(cfg.seed, "products")
    subcats = []
    for dept, cats in PRODUCT_HIERARCHY.items():
        for cat, (subs, lo, hi, margin) in cats.items():
            for sub in subs:
                sub_id = next(c["category_id"] for c in md.categories if c["category_name"] == sub)
                subcats.append((dept, cat, sub, sub_id, lo, hi, margin))
    dept_counts = {d: sum(1 for s in subcats if s[0] == d) for d in PRODUCT_HIERARCHY}

    for i in range(cfg.n_products):
        dept, _cat, sub, sub_id, lo, hi, margin = subcats[i % len(subcats)]
        brand = rng.choice([b for b in md.brands if b["primary_department"] == dept])
        supplier = rng.choice(md.suppliers)
        # Log-uniform prices: many cheap items, few expensive ones.
        price = round(lo * (hi / lo) ** rng.random()) - 0.01
        price = max(price, 4.99)
        cost = round(price * (1 - margin) * rng.uniform(0.85, 1.15), 2)
        rank = rng.random()
        md.products.append(
            {
                "product_id": 100_001 + i,
                "sku": f"RP-{100_001 + i}",
                "product_name": " ".join(
                    [brand["brand_name"], rng.choice(PRODUCT_ADJECTIVES), sub.split()[-1].rstrip("s")]
                ),
                "category_id": sub_id,
                "brand_id": brand["brand_id"],
                "supplier_id": supplier["supplier_id"],
                "vendor_sku": f"{supplier['supplier_id'][-3:]}-{rng.randint(10000, 99999)}",
                "unit_cost_usd": cost,
                "list_price_usd": price,
                "weight_kg": round(rng.uniform(0.1, 12.0), 2),
                "is_active": True,
                "created_at": created + timedelta(days=rng.randint(0, 900)),
                "updated_at": created,
                # Popularity drives demand. Department weight keeps the sales mix realistic.
                # Cheaper items sell more often than expensive ones within a subcategory.
                "_popularity": DEPARTMENT_SALES_WEIGHT[dept]
                / dept_counts[dept]
                * (0.05 + rank**3 * 4)
                * (lo / price) ** 0.6,
            }
        )
    for p in md.products:
        p["updated_at"] = p["created_at"]


def _build_locations(md: MasterData, cfg: GeneratorConfig, created: datetime) -> None:
    rng = rng_for(cfg.seed, "stores")
    store_no = 1
    for country, n_stores in STORES_PER_COUNTRY.items():
        cities = [c for c in CITIES if c[2] == country]
        weights = [c[4] for c in cities]
        # Every city gets one store first, the rest go to bigger cities.
        assigned = list(cities) + rng.choices(cities, weights, k=max(0, n_stores - len(cities)))
        for city, region, _cc, tz, _w in assigned[:n_stores]:
            store_type = rng.choices(["STANDARD", "FLAGSHIP", "OUTLET"], [0.75, 0.1, 0.15])[0]
            md.stores.append(
                {
                    "store_id": f"ST{store_no:03d}",
                    "store_name": f"RetailPulse {city} {store_type.title()} {store_no}",
                    "store_type": store_type,
                    "city": city,
                    "region": region,
                    "country_code": country,
                    "timezone": tz,
                    "opened_date": date(2010, 1, 1) + timedelta(days=rng.randint(0, 5000)),
                    "floor_area_sqm": rng.randint(600, 4000)
                    if store_type != "FLAGSHIP"
                    else rng.randint(5000, 9000),
                    "created_at": created,
                    "updated_at": created,
                }
            )
            store_no += 1
    for wh_id, (name, city, country, _regions) in WAREHOUSES.items():
        md.warehouses.append(
            {
                "warehouse_id": wh_id,
                "warehouse_name": name,
                "city": city,
                "country_code": country,
                "created_at": created,
                "updated_at": created,
            }
        )


def _build_customers(md: MasterData, cfg: GeneratorConfig) -> None:
    rng = rng_for(cfg.seed, "customers")
    fakers = {}
    for cc, (_n, _cur, locale, _f) in COUNTRIES.items():
        fakers[cc] = Faker(locale)
        fakers[cc].seed_instance(cfg.seed + len(fakers))
    country_weights = {"US": 0.62, "GB": 0.22, "DE": 0.16}
    history_start = cfg.start_date - timedelta(days=3 * 365)
    for i in range(cfg.n_customers):
        cc = rng.choices(list(country_weights), list(country_weights.values()))[0]
        fake = fakers[cc]
        cities = [c for c in CITIES if c[2] == cc]
        city = rng.choices(cities, [c[4] for c in cities])[0]
        # 80% existed before the simulation starts, 20% sign up during it.
        if rng.random() < 0.8:
            signup = history_start + timedelta(days=rng.randint(0, (cfg.start_date - history_start).days - 1))
        else:
            signup = cfg.start_date + timedelta(days=rng.randint(0, cfg.horizon_days - 1))
        signup_ts = _ts(signup, rng, 6, 23)
        first, last = fake.first_name(), fake.last_name()
        activity = rng.paretovariate(1.6)
        # Spend before the simulation starts sets the opening loyalty tier.
        tenure_years = max((cfg.start_date - signup).days, 0) / 365
        prior_spend = round(activity * tenure_years * rng.uniform(150, 600), 2)
        tier = [code for code, _n, threshold, _p in LOYALTY_TIERS if prior_spend >= threshold][-1]
        email_user = f"{first}.{last}{rng.randint(1, 999)}".lower().replace(" ", "")
        customer = {
            "customer_id": 500_001 + i,
            "first_name": first,
            "last_name": last,
            "email": f"{email_user}@{rng.choice(EMAIL_DOMAINS)}",
            "phone": fake.phone_number(),
            "address_line1": fake.street_address().replace("\n", ", "),
            "city": city[0],
            "postal_code": fake.postcode(),
            "country_code": cc,
            "loyalty_card_no": f"LC{rng.randint(10**9, 10**10 - 1)}" if rng.random() < 0.65 else None,
            "loyalty_tier": tier,
            "marketing_opt_in": rng.random() < 0.55,
            "created_at": signup_ts,
            "updated_at": signup_ts,
            # Hidden: shopping propensity and a possible move during the window (drives SCD2 history).
            "_activity": activity,
            "_prior_spend": prior_spend,
            "_move_on": cfg.start_date + timedelta(days=rng.randint(1, cfg.horizon_days - 1))
            if rng.random() < 0.32
            else None,
        }
        md.customers.append(customer)
    # A few duplicate accounts: the same person signed up twice with different email casing.
    for i in range(int(cfg.n_customers * cfg.dq_rate / 2)):
        src = md.customers[rng.randrange(len(md.customers))]
        dup = dict(src)
        dup["customer_id"] = 500_001 + cfg.n_customers + i
        dup["email"] = src["email"].upper()
        dup["loyalty_card_no"] = None
        dup["created_at"] = dup["updated_at"] = src["created_at"] + timedelta(days=rng.randint(30, 400))
        dup["_activity"] = src["_activity"] * 0.2
        dup["_prior_spend"] = 0.0
        dup["loyalty_tier"] = "T1"
        dup["_move_on"] = None
        md.customers.append(dup)


def _build_promotions(md: MasterData, cfg: GeneratorConfig) -> None:
    rng = rng_for(cfg.seed, "promotions")
    level2 = [c for c in md.categories if c["category_level"] == "CATEGORY"]
    themes = [
        "Summer Clearance",
        "Back to School",
        "Tech Week",
        "Home Refresh",
        "Autumn Style",
        "Flash Friday",
        "Loyalty Exclusive",
        "Weekend Deals",
    ]
    for i, theme in enumerate(themes, start=1):
        md.campaigns.append(
            {
                "campaign_id": f"CMP{i:02d}",
                "campaign_name": f"{theme} {cfg.start_date.year}",
                "budget_usd": rng.randrange(20_000, 250_000, 5_000),
            }
        )
    for i in range(1, cfg.n_promotions + 1):
        campaign = rng.choice(md.campaigns)
        start = cfg.start_date + timedelta(days=rng.randint(-10, cfg.horizon_days - 5))
        scope = rng.choice(level2) if rng.random() < 0.8 else None
        pct = rng.choice([10, 15, 20, 25, 30])
        md.promotions.append(
            {
                "promotion_id": f"PRM{i:03d}",
                "campaign_id": campaign["campaign_id"],
                "promotion_name": f"{scope['category_name'] if scope else 'Sitewide'} {pct}% off",
                "discount_pct": pct,
                "channel": rng.choices(["ALL", "ONLINE", "STORE"], [0.5, 0.3, 0.2])[0],
                "category_id": scope["category_id"] if scope else None,
                "country_codes": sorted(rng.sample(list(COUNTRIES), rng.randint(1, 3))),
                "start_date": start,
                "end_date": start + timedelta(days=rng.choice([3, 7, 7, 14, 21])),
            }
        )
