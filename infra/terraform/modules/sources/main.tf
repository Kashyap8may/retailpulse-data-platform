# The four RetailPulse source systems and what they need around them:
#   s3.tf          POS and promotions file drop, plus a private bucket for the simulator
#   rds.tf         orders database (PostgreSQL)
#   carrier_api.tf DynamoDB + Lambda + API Gateway
#   sftp.tf        OpenSSH on EC2 for the 3PL and supplier feeds
#   schedule.tf    starts and stops RDS and EC2 around a daily window
#   iam.tf         users for the Databricks simulator and pipelines (no access keys)
#   parameters.tf  connection details in SSM Parameter Store
#   budget.tf      monthly cost alert

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# The default VPC keeps cost at zero: no NAT gateway, and every source here is reached over
# the internet anyway, because Databricks Free Edition runs outside this account.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  p          = var.name_prefix
}
