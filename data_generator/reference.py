"""Fixed reference data: geography, product hierarchy, carriers and lookup values."""

from __future__ import annotations

COUNTRIES = {
    # code: (name, currency, faker locale, price factor applied to the USD list price)
    "US": ("United States", "USD", "en_US", 1.00),
    "GB": ("United Kingdom", "GBP", "en_GB", 0.84),
    "DE": ("Germany", "EUR", "de_DE", 0.97),
}

# (city, region, country, IANA time zone, relative population weight)
CITIES = [
    ("New York", "Northeast", "US", "America/New_York", 10),
    ("Boston", "Northeast", "US", "America/New_York", 4),
    ("Philadelphia", "Northeast", "US", "America/New_York", 4),
    ("Chicago", "Midwest", "US", "America/Chicago", 6),
    ("Minneapolis", "Midwest", "US", "America/Chicago", 3),
    ("Atlanta", "South", "US", "America/New_York", 4),
    ("Dallas", "South", "US", "America/Chicago", 5),
    ("Miami", "South", "US", "America/New_York", 4),
    ("Los Angeles", "West", "US", "America/Los_Angeles", 8),
    ("Seattle", "West", "US", "America/Los_Angeles", 4),
    ("Denver", "West", "US", "America/Denver", 3),
    ("Phoenix", "West", "US", "America/Phoenix", 3),
    ("London", "London", "GB", "Europe/London", 9),
    ("Manchester", "North England", "GB", "Europe/London", 3),
    ("Leeds", "North England", "GB", "Europe/London", 2),
    ("Birmingham", "Midlands", "GB", "Europe/London", 3),
    ("Glasgow", "Scotland", "GB", "Europe/London", 2),
    ("Edinburgh", "Scotland", "GB", "Europe/London", 2),
    ("Berlin", "North Germany", "DE", "Europe/Berlin", 5),
    ("Hamburg", "North Germany", "DE", "Europe/Berlin", 3),
    ("Cologne", "West Germany", "DE", "Europe/Berlin", 3),
    ("Dusseldorf", "West Germany", "DE", "Europe/Berlin", 2),
    ("Munich", "South Germany", "DE", "Europe/Berlin", 4),
    ("Stuttgart", "South Germany", "DE", "Europe/Berlin", 2),
]

STORES_PER_COUNTRY = {"US": 24, "GB": 9, "DE": 7}

# warehouse_id: (name, city, serves country, serves regions or None for all)
WAREHOUSES = {
    "WH-US-E": ("US East DC", "Philadelphia", "US", ["Northeast", "Midwest", "South"]),
    "WH-US-W": ("US West DC", "Phoenix", "US", ["West"]),
    "WH-GB": ("UK DC", "Birmingham", "GB", None),
    "WH-DE": ("Germany DC", "Cologne", "DE", None),
}

# department -> category -> (subcategories, min USD price, max USD price, target margin)
PRODUCT_HIERARCHY = {
    "Home": {
        "Kitchen": (["Cookware", "Small Appliances", "Tableware"], 12, 320, 0.45),
        "Bedding": (["Sheets", "Pillows", "Duvets"], 15, 220, 0.55),
        "Decor": (["Lighting", "Rugs", "Wall Art"], 10, 280, 0.60),
    },
    "Electronics": {
        "Audio": (["Headphones", "Speakers"], 25, 450, 0.30),
        "Computing": (["Laptops", "Monitors", "Computer Accessories"], 15, 1600, 0.18),
        "Mobile": (["Phone Cases", "Chargers"], 8, 90, 0.55),
        "Smart Home": (["Security Cameras", "Smart Plugs"], 15, 250, 0.35),
    },
    "Apparel": {
        "Men": (["Men Shirts", "Men Trousers", "Men Outerwear"], 15, 260, 0.58),
        "Women": (["Dresses", "Women Tops", "Women Outerwear"], 15, 280, 0.60),
        "Footwear": (["Sneakers", "Boots"], 35, 220, 0.50),
        "Kids": (["Kids Tops", "Kids Bottoms"], 8, 60, 0.55),
    },
}

DEPARTMENT_SALES_WEIGHT = {"Home": 0.35, "Electronics": 0.25, "Apparel": 0.40}

# carrier_id: (name, countries served, on-time probability)
CARRIERS = {
    "SWS": ("SwiftShip", ["US"], 0.93),
    "PPX": ("ParcelPro", ["US", "GB"], 0.86),
    "EUX": ("EuroExpress", ["GB", "DE"], 0.90),
}

# service level: (promised business days, share of orders, shipping fee in USD)
SERVICE_LEVELS = {
    "STANDARD": (5, 0.78, 4.99),
    "EXPRESS": (2, 0.22, 12.99),
}

LOYALTY_TIERS = [
    # tier_code, tier_name, minimum lifetime spend in USD, discount percentage
    ("T1", "Bronze", 0, 0),
    ("T2", "Silver", 1000, 3),
    ("T3", "Gold", 3000, 5),
    ("T4", "Platinum", 7500, 8),
]

PAYMENT_METHODS = {
    "US": [("card", 0.70), ("paypal", 0.20), ("apple_pay", 0.10)],
    "GB": [("card", 0.65), ("paypal", 0.20), ("klarna", 0.15)],
    "DE": [("card", 0.35), ("paypal", 0.35), ("klarna", 0.20), ("sepa_debit", 0.10)],
}

POS_TENDER_TYPES = [("CARD", 0.78), ("CASH", 0.15), ("GIFTCARD", 0.03), ("MOBILE", 0.04)]

RETURN_REASONS = [
    ("WRONG_SIZE", 0.35),
    ("DAMAGED", 0.12),
    ("NOT_AS_DESCRIBED", 0.18),
    ("CHANGED_MIND", 0.28),
    ("LATE_DELIVERY", 0.07),
]

# Higher return rates in apparel, lower in home.
RETURN_RATE_BY_DEPARTMENT = {"Home": 0.04, "Electronics": 0.06, "Apparel": 0.14}
