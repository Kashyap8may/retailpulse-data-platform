# Handoff: project state as of 2026-10-30

This file carries the context from the planning sessions so work can continue in a local Antigravity session. Update it whenever a milestone finishes or a decision changes.

## Where things stand

| Milestone | Status | Notes |
|---|---|---|
| M0 Scaffold | Done, on `main` (commit `f31db55`) | Tagged `m0` |
| M1 Data generator | Done, on `main` (commit `9134e22`), CI green | Tagged `m1` |
| M2 AWS sources (Terraform) | Done 2026-11-02 | Every source tested from a laptop and from Databricks serverless |
| M3 Load the sources | Not started | |
| M4 Databricks foundation | Not started | Design depends on the connectivity check |
| M5 Bronze, M6 Silver, M7 Gold | Owner's own work | Do not implement |
| M8 Orchestration and ops, M9 Showcase | Not started | |

## Decisions made

| Decision | Choice | Why |
|---|---|---|
| Business case | RetailPulse, omnichannel retailer, 6 business questions (see README) | Every question needs at least two sources, which forces real conformance work |
| Sources | RDS PostgreSQL, carrier REST API (API Gateway + Lambda + DynamoDB), S3 file drops, SFTP on EC2, plus the free Frankfurter FX API | Four different types and ingestion patterns |
| SFTP server | OpenSSH on a small EC2 instance; Transfer Family only as an optional toggle | Cost, see `docs/adr/0001-sftp-on-ec2.md` |
| Streaming (Kinesis clickstream) | Stretch goal, not now | Keeps scope and cost down |
| Region | `us-east-1` (assumed, owner has not objected) | |
| Databricks | Free Edition (owner's existing workspace) | |
| Unity Catalog layout | Catalogs `retailpulse_dev` and `retailpulse_prod`, schemas `bronze`, `silver`, `gold` | One catalog per environment. Free Edition has one metastore; check that two catalogs are allowed, otherwise use one catalog with `dev_`/`prod_` schema prefixes |
| Milestone tags | Added by the owner locally | |
| Medallion layers | Owner builds bronze, silver and gold | Assistants provide only the sources, the simulator and the contracts |
| Generator calendar | Fixed `horizon_days` (365) | Adding a day must not rewrite published days; a test enforces it |
| Daily feed | Pre-generate the year once, publish one day per run | Replaying a full year takes about 11 minutes and grows with every day |
| Cost | Target $5 to $8 a month, alert at $10 | RDS and EC2 run only in a daily window; Parameter Store instead of Secrets Manager |

## The open question: how data gets from AWS into Databricks Free Edition

Free Edition compute is serverless, and its outbound internet is limited to trusted domains that Databricks does not publish. So Databricks may not be able to pull straight from RDS (port 5432), the API or SFTP (port 22).

**Step 1: run the check.** Import `databricks/notebooks/00_connectivity_check.py` into the workspace, run it on serverless, and note the results. It needs no credentials and changes nothing. It reports:
1. whether `SHOW STORAGE CREDENTIALS` / `SHOW EXTERNAL LOCATIONS` work (can we point Unity Catalog at our own S3 bucket?),
2. which HTTPS hosts are reachable (FX API, a generic site, AWS S3, STS and API Gateway endpoints, PyPI),
3. whether raw TCP on ports 5432, 22 and 443 can leave the workspace.

**Results (run on serverless, 2026-10-30):**

| Check | Result |
|---|---|
| `SHOW STORAGE CREDENTIALS`, `SHOW EXTERNAL LOCATIONS` | Both run, 0 rows. Creating them is not yet tested |
| `SHOW CATALOGS` | `databricks_simulated_retail_customer_data`, `samples`, `system`, `workspace` |
| HTTPS: FX API, httpbin, S3, STS, PyPI | HTTP 200 |
| HTTPS: API Gateway domain | HTTP 403, so the host is reachable |
| TCP to `portquiz.net` on 5432, 22, 443 | All connect |

Still to prove: creating a storage credential and external location, creating two catalogs, and a real connection to RDS and the SFTP server (the TCP test only reached a public test host).

**Step 2: choose the bridge.** The plan works for any result:

- On AWS, small Lambda jobs (scheduled by EventBridge) extract each source into an **S3 landing bucket**: incremental Postgres extract on `updated_at`, a paged API pull, an SFTP pull with archive, and the POS files already land in S3. This is a common production pattern anyway.
- **If Databricks can use an external location on S3:** Auto Loader reads the landing bucket directly. Create the storage credential with an IAM role that trusts Databricks (no access keys).
- **If it cannot:** one more Lambda pushes each new landing file into a Unity Catalog volume through the Databricks Files API (`PUT /api/2.0/fs/files/Volumes/...`), using a Databricks token kept in AWS Secrets Manager. Auto Loader then reads the volume.
- **If raw TCP to 5432 works:** the Postgres source can also be read with JDBC or Lakehouse Federation from Databricks, which is a nicer showcase. Keep the S3 path as the fallback.

Bronze, silver and the gold model are the same in every case.

## Next steps (M2 onwards)

1. Connectivity check: done, results above.
2. **M2 is deployed.** State is in `retailpulse-tfstate-<account>`. From a laptop: Postgres 17.9 over TLS works and non-TLS is refused; the API returns 200 with the key, 403 without and 400 on bad input; SFTP key login, upload and delete work, while shell and password logins are refused. From Databricks serverless (`01_source_connectivity_test.py`, using the `pipelines` key in secret scope `retailpulse-dev`): S3 sources readable, simulator bucket denied, API 200, Postgres through psycopg and Spark JDBC, SFTP login and listing all pass. First apply note: RDS creation hit Terraform's 50-minute wait although the instance was ready; the resource was untainted rather than replaced. The original M2 brief follows for reference.
3. **M2 brief, Terraform in `infra/terraform/`** (modules `aws/` and later `databricks/`, environments under `envs/dev`):
   - remote state bucket and lock table (bootstrapped separately),
   - S3 buckets: `landing` (raw drops and extracts) and `pos-drop` (or one bucket with prefixes), versioning on, lifecycle rules,
   - RDS PostgreSQL `db.t4g.micro`, password in Secrets Manager, security group limited to the owner's IP and the Lambdas,
   - carrier API: DynamoDB table `shipments` (PK `shipment_id`, GSI on `updated_at` bucket), Lambda in `services/carrier_api/` serving `GET /shipments?updated_since=&page_token=` behind API Gateway with an API key and usage plan,
   - SFTP: EC2 `t4g.nano`/`t3.micro` with OpenSSH, chrooted SFTP user, key-only login, key in Secrets Manager,
   - IAM roles for the extract Lambdas (and for Databricks if external locations work),
   - AWS Budgets alert, tags on everything, a teardown target.
4. **M3, loaders:** load `output/postgres/*.csv` into RDS using `data_generator/sources/postgres_schema.sql` (load order is `LOAD_ORDER` in `sources/postgres.py`), `shipments.jsonl` into DynamoDB, POS and promotions files into S3, SFTP files onto the server. Then a daily simulator: the generator is deterministic and `as_of` aware (`postgres_tables(md, sim, as_of)`, `shipment_documents(sim, as_of, ...)`), so day N's changes are the rows whose `updated_at` falls on day N; `sim.customer_versions` holds every customer change. POS files are already partitioned by `landing_date`.
5. M4 onwards as in `docs/project-plan.md`.

## Facts about the generated data worth knowing

- Default run: 90 days from 2026-07-01, about 43k customers, 137k online orders, 230k order lines, 130k shipments, 1M POS lines, 360 inventory files, 90 supplier delivery files. A full year (365 days, 1.5 GB) reaches about 50k customers, 611k orders and 4.2M POS lines.
- Warehouse stock-outs run at roughly 1.5 to 2% of SKU-days, which gives the stock-out question (Q2) something to find. About 11% of deliveries arrive after the promised date.
- Deliberate data-quality problems are listed in the README under "Data problems built in on purpose". The supplier delivery feed switches from layout v1 to v2 on day 45.
- Key mismatches on purpose: POS knows customers only by `loyalty_card_no`; supplier files use `vendor_sku`, mapped to our product through `products.vendor_sku`; online orders use `product_id`, POS uses `sku`.

## Owner preferences

- Wants clear progress showcased on GitHub: README updated at every step.
- Builds locally in Antigravity and hosts on GitHub (`Kashyap8may/retailpulse-data-platform`).
- Plain, step-by-step explanations; commit at each milestone.
