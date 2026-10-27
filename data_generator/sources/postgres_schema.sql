-- RetailPulse e-commerce and ERP database (source 1, RDS PostgreSQL).
-- Rows are updated in place; every table carries updated_at for incremental extraction.

CREATE SCHEMA IF NOT EXISTS shop;
SET search_path TO shop;

CREATE TABLE IF NOT EXISTS product_categories (
    category_id         integer PRIMARY KEY,
    parent_category_id  integer REFERENCES product_categories (category_id),
    category_name       varchar(80)  NOT NULL,
    category_level      varchar(20)  NOT NULL CHECK (category_level IN ('DEPARTMENT', 'CATEGORY', 'SUBCATEGORY')),
    created_at          timestamptz  NOT NULL,
    updated_at          timestamptz  NOT NULL
);

CREATE TABLE IF NOT EXISTS brands (
    brand_id            integer PRIMARY KEY,
    brand_name          varchar(80)  NOT NULL UNIQUE,
    primary_department  varchar(40)  NOT NULL,
    created_at          timestamptz  NOT NULL,
    updated_at          timestamptz  NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     varchar(10)  PRIMARY KEY,
    supplier_name   varchar(120) NOT NULL,
    country_code    char(2)      NOT NULL,
    lead_time_days  integer      NOT NULL,
    contact_email   varchar(160),
    created_at      timestamptz  NOT NULL,
    updated_at      timestamptz  NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id      integer PRIMARY KEY,
    sku             varchar(20)   NOT NULL UNIQUE,
    product_name    varchar(160)  NOT NULL,
    category_id     integer       NOT NULL REFERENCES product_categories (category_id),
    brand_id        integer       NOT NULL REFERENCES brands (brand_id),
    supplier_id     varchar(10)   NOT NULL REFERENCES suppliers (supplier_id),
    vendor_sku      varchar(20)   NOT NULL,
    unit_cost_usd   numeric(10,2) NOT NULL,
    list_price_usd  numeric(10,2) NOT NULL,
    weight_kg       numeric(6,2),
    is_active       boolean       NOT NULL DEFAULT true,
    created_at      timestamptz   NOT NULL,
    updated_at      timestamptz   NOT NULL
);

CREATE TABLE IF NOT EXISTS stores (
    store_id        varchar(10)  PRIMARY KEY,
    store_name      varchar(120) NOT NULL,
    store_type      varchar(20)  NOT NULL,
    city            varchar(80)  NOT NULL,
    region          varchar(80)  NOT NULL,
    country_code    char(2)      NOT NULL,
    timezone        varchar(40)  NOT NULL,
    opened_date     date         NOT NULL,
    floor_area_sqm  integer,
    created_at      timestamptz  NOT NULL,
    updated_at      timestamptz  NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id    varchar(10)  PRIMARY KEY,
    warehouse_name  varchar(80)  NOT NULL,
    city            varchar(80)  NOT NULL,
    country_code    char(2)      NOT NULL,
    created_at      timestamptz  NOT NULL,
    updated_at      timestamptz  NOT NULL
);

CREATE TABLE IF NOT EXISTS loyalty_tiers (
    tier_code               varchar(4)  PRIMARY KEY,
    tier_name               varchar(20) NOT NULL,
    min_lifetime_spend_usd  integer     NOT NULL,
    discount_pct            integer     NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id       integer PRIMARY KEY,
    first_name        varchar(80),
    last_name         varchar(80),
    email             varchar(160),
    phone             varchar(40),
    address_line1     varchar(200),
    city              varchar(80),
    postal_code       varchar(20),
    country_code      char(2)     NOT NULL,
    loyalty_card_no   varchar(20),
    loyalty_tier      varchar(4)  NOT NULL REFERENCES loyalty_tiers (tier_code),
    marketing_opt_in  boolean     NOT NULL,
    created_at        timestamptz NOT NULL,
    updated_at        timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id                 bigint PRIMARY KEY,
    order_number             varchar(20)   NOT NULL UNIQUE,
    customer_id              integer       NOT NULL REFERENCES customers (customer_id),
    order_ts                 timestamptz   NOT NULL,
    channel                  varchar(10)   NOT NULL,
    status                   varchar(20)   NOT NULL,
    currency                 char(3)       NOT NULL,
    shipping_service         varchar(20)   NOT NULL,
    ship_to_city             varchar(80),
    ship_to_postal_code      varchar(20),
    ship_to_country          char(2)       NOT NULL,
    fulfilment_warehouse_id  varchar(10)   REFERENCES warehouses (warehouse_id),
    subtotal_amount          numeric(12,2) NOT NULL,
    discount_amount          numeric(12,2) NOT NULL,
    shipping_amount          numeric(12,2) NOT NULL,
    tax_amount               numeric(12,2) NOT NULL,
    total_amount             numeric(12,2) NOT NULL,
    created_at               timestamptz   NOT NULL,
    updated_at               timestamptz   NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id    bigint PRIMARY KEY,
    order_id         bigint        NOT NULL REFERENCES orders (order_id),
    line_number      integer       NOT NULL,
    product_id       integer       NOT NULL REFERENCES products (product_id),
    quantity         integer       NOT NULL,
    unit_price       numeric(10,2) NOT NULL,
    discount_amount  numeric(10,2) NOT NULL,
    promotion_id     varchar(10),
    created_at       timestamptz   NOT NULL,
    updated_at       timestamptz   NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id          bigint PRIMARY KEY,
    order_id            bigint        NOT NULL REFERENCES orders (order_id),
    payment_method      varchar(20)   NOT NULL,
    payment_type        varchar(10)   NOT NULL,
    status              varchar(20)   NOT NULL,
    amount              numeric(12,2) NOT NULL,
    currency            char(3)       NOT NULL,
    provider_reference  varchar(40),
    created_at          timestamptz   NOT NULL,
    updated_at          timestamptz   NOT NULL
);

CREATE TABLE IF NOT EXISTS returns (
    return_id      bigint PRIMARY KEY,
    order_id       bigint        NOT NULL REFERENCES orders (order_id),
    order_item_id  bigint        NOT NULL REFERENCES order_items (order_item_id),
    quantity       integer       NOT NULL,
    reason_code    varchar(30)   NOT NULL,
    status         varchar(20)   NOT NULL,
    refund_amount  numeric(12,2) NOT NULL,
    currency       char(3)       NOT NULL,
    created_at     timestamptz   NOT NULL,
    updated_at     timestamptz   NOT NULL
);

-- Indexes that support incremental extraction on updated_at.
CREATE INDEX IF NOT EXISTS ix_customers_updated_at   ON customers (updated_at);
CREATE INDEX IF NOT EXISTS ix_orders_updated_at      ON orders (updated_at);
CREATE INDEX IF NOT EXISTS ix_order_items_updated_at ON order_items (updated_at);
CREATE INDEX IF NOT EXISTS ix_payments_updated_at    ON payments (updated_at);
CREATE INDEX IF NOT EXISTS ix_returns_updated_at     ON returns (updated_at);
