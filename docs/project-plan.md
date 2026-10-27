# Project plan

The living plan, with diagrams, is kept as a shared document: [RetailPulse: Data Engineering Project Plan](https://claude.ai/artifact/3NSGVjb8x1vrbdZSTvMbsZ). This file is the summary kept with the code.

## Scope

- Four AWS source types (relational database, REST API, S3 file drop, SFTP) plus a public FX API. A Kinesis clickstream source is a stretch goal.
- Ingestion into Databricks with Unity Catalog: one catalog per environment (`retailpulse_dev`, `retailpulse_prod`) with schemas `bronze`, `silver` and `gold`.
- Bronze and silver are built in this repository. Gold, the snowflake-schema model, is built by the project owner.

## Target gold model (snowflake schema)

| Fact | Grain | Main sources | Key dimensions |
|---|---|---|---|
| fact_sales_line | one online order line or POS line | RDS orders, S3 POS files, FX rates | product, store, customer, date, channel, promotion, currency |
| fact_shipment | one shipment | Carrier API, RDS orders | carrier, customer city, date |
| fact_inventory_daily | one product per warehouse per day | SFTP 3PL inventory feed | product, warehouse, date |
| fact_po_receipt | one purchase-order line received | SFTP supplier receipts feed | product, supplier, date |
| fact_returns | one returned line | RDS returns | product, customer, date, return reason |

Dimensions are normalized into hierarchies:

- product → subcategory → category → department, and product → brand, product → supplier → country
- store → city → region → country (customer and warehouse also point at city)
- customer (SCD Type 2) → loyalty tier
- date → month → year
- promotion → campaign
- channel, currency, carrier → carrier service

## Milestones

Each milestone ends with a commit, a git tag (`m0`, `m1`, ...) and an update to the progress table in the README.

| Milestone | Delivers |
|---|---|
| M0 Scaffold | Repo layout, README, plan, CI skeleton |
| M1 Data generator | Seeded master data and generators for every source, with tests |
| M2 AWS sources | Terraform for S3, RDS, carrier API, SFTP server, secrets, IAM, budget alert |
| M3 Load the sources | Seed 90 days of history, then a daily simulator |
| M4 Databricks foundation | Catalogs, schemas, storage credential, external locations, secret scope |
| M5 Bronze | One ingestion job per source |
| M6 Silver | Cleaning, dedupe, conformed keys, SCD2, quarantine tables |
| M7 Gold | Snowflake model (owner) |
| M8 Orchestration and ops | End-to-end workflow, alerts, audit table, CI deploys |
| M9 Showcase | Dashboard, screenshots, cost notes |
