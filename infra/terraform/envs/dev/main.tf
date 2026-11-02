# Dev environment: the RetailPulse source systems in one AWS account.
#
#   terraform -chdir=infra/terraform/envs/dev init -backend-config=backend.hcl
#   terraform -chdir=infra/terraform/envs/dev plan
#
# backend.hcl and terraform.tfvars are git-ignored; copy them from the .example files.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    key          = "dev/sources.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "retailpulse"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

module "sources" {
  source = "../../modules/sources"

  name_prefix            = "retailpulse-dev"
  parameter_prefix       = "/retailpulse/dev"
  alert_email            = var.alert_email
  monthly_budget_usd     = var.monthly_budget_usd
  db_ingress_cidrs       = var.db_ingress_cidrs
  sftp_ingress_cidrs     = var.sftp_ingress_cidrs
  schedule_enabled       = var.schedule_enabled
  window_start_cron      = var.window_start_cron
  window_stop_cron       = var.window_stop_cron
  carrier_api_source_dir = "${path.root}/../../../../services/carrier_api"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "alert_email" {
  type = string
}

variable "monthly_budget_usd" {
  type    = number
  default = 10
}

# Databricks serverless egress has no published fixed range, so dev opens these widely.
variable "db_ingress_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "sftp_ingress_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "schedule_enabled" {
  type    = bool
  default = true
}

variable "window_start_cron" {
  type    = string
  default = "cron(0 6 * * ? *)"
}

variable "window_stop_cron" {
  type    = string
  default = "cron(0 8 * * ? *)"
}

output "sources" {
  value = module.sources
}
