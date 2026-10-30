# Databricks notebook source
# MAGIC %md
# MAGIC # RetailPulse: Free Edition connectivity check
# MAGIC Run every cell on serverless compute and share the printed results.
# MAGIC Nothing here needs credentials, and nothing is created or changed.

# COMMAND ----------

# 1. Can this workspace use external storage in Unity Catalog?
for stmt in ["SHOW STORAGE CREDENTIALS", "SHOW EXTERNAL LOCATIONS", "SHOW CATALOGS"]:
    try:
        rows = spark.sql(stmt).collect()
        print(f"OK   {stmt}: {len(rows)} rows -> {[r[0] for r in rows][:10]}")
    except Exception as e:
        print(f"FAIL {stmt}: {str(e).splitlines()[0][:200]}")

# COMMAND ----------

# 2. Outbound HTTPS: which kinds of hosts can serverless reach?
import requests

urls = {
    "public FX API": "https://api.frankfurter.dev/v1/latest",
    "generic public site": "https://httpbin.org/get",
    "AWS S3 endpoint": "https://s3.us-east-1.amazonaws.com",
    "AWS STS endpoint": "https://sts.us-east-1.amazonaws.com",
    "AWS API Gateway domain": "https://apigateway.us-east-1.amazonaws.com",
    "PyPI": "https://pypi.org/simple/requests/",
}
for name, url in urls.items():
    try:
        r = requests.get(url, timeout=10)
        print(f"OK   {name}: HTTP {r.status_code}")
    except Exception as e:
        print(f"FAIL {name}: {type(e).__name__}: {str(e)[:150]}")

# COMMAND ----------

# 3. Raw TCP: can serverless open a Postgres (5432) or SFTP (22) connection to the internet?
# portquiz.net answers on every port, so a failure here means the port is blocked.
import socket

for port in [5432, 22, 443]:
    try:
        with socket.create_connection(("portquiz.net", port), timeout=8):
            print(f"OK   TCP {port}")
    except Exception as e:
        print(f"FAIL TCP {port}: {type(e).__name__}: {str(e)[:150]}")
