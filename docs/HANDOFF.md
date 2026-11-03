# Handoff: project state as of 2026-11-03

Read with `CLAUDE.md`. Update this file whenever a milestone finishes or a decision changes.

## Where things stand

| Milestone | Status | Notes |
|---|---|---|
| M0 Scaffold | Done | Tagged `m0` |
| M1 Data generator | Done | Tagged `m1` |
| M2 AWS sources (Terraform) | Done 2026-11-02 | Tagged `m2`; every source tested from a laptop and from Databricks serverless |
| M3 Load the sources | Done 2026-11-03 | History 2026-06-30 to 2026-11-02 published; daily job scheduled |
| M4 Databricks foundation | Next, owner | Catalogs, schemas, secret scope use |
| M5 Bronze, M6 Silver, M7 Gold | Owner's own work | Do not implement |
| M8 Orchestration and ops, M9 Showcase | Not started | |

## How the sources get their data

1. `python -m data_generator.daily --out output/daily` simulates the fixed one-year calendar (2026-07-01 to 2027-06-30) once and writes one folder per UTC day with only that day's changes. The first folder, 2026-06-30, is the opening state. Tests prove that replaying the days rebuilds exactly what `generate()` shows.
2. The folders live in the private simulator bucket under `days/` (uploaded with `aws s3 sync output/daily s3://<simulator bucket>/days/`, 3 GB, 18,415 objects).
3. `python -m data_generator.publish` applies every day after `state/published_through` (in the simulator bucket) up to yesterday: Postgres upserts by primary key in one transaction per day, DynamoDB puts, S3 copies, SFTP uploads as `.part` then rename. Every write replaces by key, so rerunning is safe. It starts RDS and the SFTP server if they are stopped.
4. The Databricks job `retailpulse-source-simulator` (bundle `databricks.yml`, resource `databricks/resources/source_simulator.yml`) runs it daily at 06:10 UTC on serverless with the `simulator` IAM user's key from secret scope `retailpulse-dev`. Deploy with `databricks bundle deploy`.

The calendar ends on 2027-06-30. To go further, raise `horizon_days`, regenerate, re-upload and republish from scratch (the data changes, so the sources must be reloaded).

## Verified on 2026-11-03

Published through 2026-11-02, then every source compared with the day folders: all 12 Postgres tables (43,637 customers, 194,797 orders, 329,009 order lines, 215,560 payments, 23,628 returns), 185,537 DynamoDB shipments, 4,895 S3 files and 625 SFTP files match exactly, with no leftover `.part` files. From Databricks as the read-only `pipelines` user: S3, the API, Postgres through psycopg and Spark JDBC with the `retailpulse_reader` login, and SFTP all work, and the admin password and simulator bucket name are refused.

## Incidents and lessons

- **First catch-up hung for 20 hours.** Run from a laptop, the publisher stalled inside a Postgres COPY after four days and only failed when the 08:00 UTC window stopped RDS. A rerun of the same days worked, so the cause was most likely a silently dropped connection. The publisher now uses TCP keepalives, `statement_timeout` and `idle_in_transaction_session_timeout` (5 minutes each), and `--verbose` logs every table. Catch-ups should run in Databricks: 117 days took 17 minutes there against about 45 seconds a day from the laptop.
- **First apply:** RDS creation hit Terraform's 50-minute wait although the instance was ready; the resource was untainted rather than replaced.
- **Windows:** PowerShell 5.1 splits `-out=dev.tfplan` at the dot (quote such arguments), and `.gitattributes` keeps LF line endings so the EC2 user data and the Lambda zip do not change on a Windows checkout.

## Decisions made

| Decision | Choice | Why |
|---|---|---|
| Business case | RetailPulse, omnichannel retailer, 6 business questions (see README) | Every question needs at least two sources |
| Sources | RDS PostgreSQL, carrier REST API (API Gateway + Lambda + DynamoDB), S3 file drop, SFTP on EC2, plus the free Frankfurter FX API | Four source types and ingestion patterns |
| Databricks to AWS | Direct pulls from Databricks serverless | The 2026-10-30 check showed HTTPS and TCP 5432 and 22 all reachable from Free Edition |
| SFTP server | OpenSSH on EC2; Transfer Family not used | Cost, see `docs/adr/0001-sftp-on-ec2.md` |
| Medallion layers | Owner builds bronze, silver and gold | Assistants provide only the sources, the simulator and the contracts |
| Generator calendar | Fixed `horizon_days` (365) | Adding a day must not rewrite published days; a test enforces it |
| Daily feed | Pre-generate the year once, publish day by day | Replaying a year takes 22 minutes and grows each day |
| Cost | Target $5 to $8 a month, Budgets alert at $10 | RDS and EC2 run 06:00 to 08:00 UTC only; Parameter Store instead of Secrets Manager |
| Access | `pipelines` IAM user reads an allow-list of parameters; `retailpulse_reader` is read-only in Postgres | Pipelines must not see the admin password or the pre-generated future |
| Unity Catalog layout | Catalogs `retailpulse_dev` and `retailpulse_prod`, schemas `bronze`, `silver`, `gold` | Not yet created; Free Edition may allow only one catalog, in which case use schema prefixes |

## Next steps

1. Owner: M4 and bronze. Everything the pipelines need is in the README section "Reading the sources".
2. Watch the first scheduled runs of `retailpulse-source-simulator` (06:10 UTC daily). A failed run catches up on the next one.
3. Possible extras: occasional hard deletes in Postgres (so `updated_at` pulls miss something, as in real life), and rare bad days (a missing file, a late carrier batch) for alerting practice.

## Facts about the generated data worth knowing

- The full year reaches about 50k customers, 611k orders and 4.2M POS lines.
- Warehouse stock-outs run at roughly 1.5 to 2% of SKU-days. About 11% of deliveries arrive after the promised date.
- Deliberate data-quality problems are listed in the README under "Data problems built in on purpose". The supplier delivery feed switches from layout v1 to v2 on day 45 (2026-08-15).
- Key mismatches on purpose: POS knows customers only by `loyalty_card_no`; supplier files use `vendor_sku`, mapped through `products.vendor_sku`; online orders use `product_id`, POS uses `sku`.

## Owner preferences

- Wants clear progress showcased on GitHub: README updated at every step.
- Builds locally and hosts on GitHub (`Kashyap8may/retailpulse-data-platform`).
- Plain, step-by-step explanations; commit at each milestone.
