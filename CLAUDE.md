# RetailPulse Data Platform: instructions for AI coding assistants

Read this first, then `docs/HANDOFF.md` for the current state and next steps.

## What this project is

A portfolio data engineering project made to look like production. Four different AWS source systems feed a Databricks lakehouse with a medallion layout (bronze, silver, gold). The gold layer is a snowflake-schema model. The business case is RetailPulse, a fictional retailer with 40 stores and an online shop in the US, UK and Germany. The full business case and the six business questions are in `README.md`.

## Ground rules from the owner

- **The owner builds the whole medallion architecture (bronze, silver and gold, milestones M5 to M7) personally.** Never implement those layers. Assistants build the AWS sources, the daily source simulator and the data contracts. `databricks/gold/` is reserved for the owner.
- **Commit at the end of every milestone and update `README.md` every time**, including the Progress table. The README is the project's showcase.
- **Milestones are tagged `m0`, `m1`, ...** The owner adds tags locally: `git tag mN <sha> && git push origin --tags`.
- **Ask before pushing** to GitHub or opening a pull request.
- **Never put credentials in code, chat or commits.** AWS credentials come from `aws configure` or AWS SSO, Databricks from `databricks auth login`, runtime secrets from AWS Secrets Manager and a Databricks secret scope. Never ask the owner to paste keys.
- Keep generated data out of git (`output/` is ignored).

## Platform constraints

- **Databricks is Free Edition**, not a workspace in the owner's AWS account. It is serverless only, outbound internet from compute is limited to a short, unpublished list of trusted domains, and there is one SQL warehouse (2X-Small), at most 5 concurrent job tasks and one active pipeline per pipeline type. Whether it can create a storage credential and external location for the owner's own S3 bucket is not yet confirmed. See `docs/HANDOFF.md` for the plan that works either way.
- AWS region: `us-east-1` unless the owner says otherwise.
- Cost matters: prefer resources that can be stopped (small EC2, db.t4g.micro RDS) and keep `make down`-style teardown in mind. Do not create AWS Transfer Family by default (about $0.30 per hour while it exists; see `docs/adr/0001-sftp-on-ec2.md`).

## Code conventions

- Python 3.11 or newer. Lint and format with ruff (`line-length = 110`), test with pytest. CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check` and `pytest`; keep it green.
- `make install`, `make lint`, `make test`, `make generate` (90 days, about 90 seconds), `make generate-small` (a few seconds).
- The data generator is deterministic: the same seed must give byte-identical output (a test checks this). Use `rng_for(seed, ...)` from `data_generator/rng.py` for any new randomness, never the global `random`.
- Every source feed has a contract in `contracts/`. If you change a writer's columns, update the contract; `tests/test_contracts.py` enforces it.
- Comments explain why, not what. Match the style of the surrounding code.

## Repository map

```
data_generator/
  config.py            volumes, dates, data-quality rate, supplier v2 cut-over day
  reference.py         fixed geography, product hierarchy, carriers, tiers
  master.py            products, stores, customers, suppliers, promotions (shared keys)
  activity/simulation.py  day-by-day simulation: orders, POS, shipments, returns, stock, POs
  sources/             one writer per source + postgres_schema.sql (DDL for RDS)
  simulate.py          CLI: python -m data_generator.simulate --out output [--scale 0.05 --days 14]
  daily.py             CLI: the year split into one folder of changes per day (uploaded to the simulator bucket)
  publish.py           CLI: applies pending days to the live sources (run daily by the Databricks job)
contracts/             YAML data contract per feed
docs/                  project-plan.md, adr/, HANDOFF.md
databricks.yml         Asset Bundle; databricks/resources/ holds the job definitions
databricks/simulator/  entry point of the retailpulse-source-simulator job
databricks/notebooks/  00_connectivity_check.py, 01_source_connectivity_test.py
infra/terraform/       bootstrap (state bucket), modules/sources, envs/dev
infra/scripts/         store-aws-key-in-databricks.ps1 (IAM key straight into the secret scope)
services/carrier_api/  Lambda handler for the mock carrier API
databricks/gold/       reserved for the owner's snowflake model
tests/
```
