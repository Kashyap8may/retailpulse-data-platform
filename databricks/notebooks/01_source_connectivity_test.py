# Databricks notebook source
# MAGIC %md
# MAGIC # RetailPulse: can Databricks reach every AWS source?
# MAGIC Uses the read-only `pipelines` IAM user from the `retailpulse-dev` secret scope, reads the
# MAGIC connection details from Parameter Store, and touches each source once. It writes nothing.
# MAGIC RDS and the SFTP server must be running (daily window, or `make sources-up`).

# COMMAND ----------

# MAGIC %pip install --quiet paramiko "psycopg[binary]"

# COMMAND ----------

import io
import json

import boto3
import paramiko
import psycopg
import requests

SCOPE = "retailpulse-dev"
PREFIX = "/retailpulse/dev"

session = boto3.Session(
    aws_access_key_id=dbutils.secrets.get(SCOPE, "aws_access_key_id"),
    aws_secret_access_key=dbutils.secrets.get(SCOPE, "aws_secret_access_key"),
    region_name="us-east-1",
)
ssm = session.client("ssm")


def param(name, secret=False):
    return ssm.get_parameter(Name=f"{PREFIX}/{name}", WithDecryption=secret)["Parameter"]["Value"]


results = {}


def check(name, fn):
    try:
        results[name] = f"OK   {fn()}"
    except Exception as exc:
        results[name] = f"FAIL {type(exc).__name__}: {str(exc)[:200]}"


# COMMAND ----------


def s3_sources():
    resp = session.client("s3").list_objects_v2(Bucket=param("s3/sources_bucket"), MaxKeys=5)
    return f"listed sources bucket, {resp['KeyCount']} keys"


def restricted_parameters_are_hidden():
    # The pipelines user must not read the admin password or learn where the simulator keeps
    # the future; both reads should be refused.
    for name in ["postgres/password", "s3/simulator_bucket"]:
        try:
            param(name, secret=True)
        except ssm.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] != "AccessDeniedException":
                raise
        else:
            raise RuntimeError(f"pipelines user can read {name}")
    return "admin password and simulator bucket are refused, as intended"


def carrier_api():
    resp = requests.get(
        param("carrier_api/url"),
        params={"limit": 5},
        headers={"x-api-key": param("carrier_api/api_key", secret=True)},
        timeout=20,
    )
    resp.raise_for_status()
    return f"HTTP {resp.status_code}, {len(resp.json()['shipments'])} shipments"


def postgres():
    with psycopg.connect(
        host=param("postgres/host"),
        port=int(param("postgres/port")),
        dbname=param("postgres/database"),
        user=param("postgres/reader_username"),
        password=param("postgres/reader_password", secret=True),
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        version = conn.execute("select version()").fetchone()[0]
        orders = conn.execute("select count(*) from shop.orders").fetchone()[0]
    return f"{version.split(',')[0]}, {orders} orders visible to the reader"


def postgres_jdbc():
    url = f"jdbc:postgresql://{param('postgres/host')}:{param('postgres/port')}/{param('postgres/database')}"
    df = (
        spark.read.format("jdbc")
        .option("url", f"{url}?sslmode=require")
        .option("user", param("postgres/reader_username"))
        .option("password", param("postgres/reader_password", secret=True))
        .option("query", "select count(*) as n from shop.customers")
        .load()
    )
    return f"spark JDBC read {df.collect()[0]['n']} customers"


def sftp():
    key = paramiko.Ed25519Key.from_private_key(io.StringIO(param("sftp/private_key", secret=True)))
    with paramiko.SSHClient() as client:
        # Demo only: the host key changes if the server is rebuilt. Production would pin it.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            param("sftp/host"),
            port=int(param("sftp/port")),
            username=param("sftp/username"),
            pkey=key,
            timeout=15,
            allow_agent=False,
            look_for_keys=False,
        )
        with client.open_sftp() as channel:
            return f"listed {sorted(channel.listdir('.'))}"


for name, fn in [
    ("s3 sources bucket", s3_sources),
    ("restricted parameters", restricted_parameters_are_hidden),
    ("carrier api", carrier_api),
    ("postgres (psycopg)", postgres),
    ("postgres (spark jdbc)", postgres_jdbc),
    ("sftp", sftp),
]:
    check(name, fn)

for name, outcome in results.items():
    print(f"{name:<24} {outcome}")

# COMMAND ----------

dbutils.notebook.exit(json.dumps(results))
