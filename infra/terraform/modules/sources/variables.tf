variable "name_prefix" {
  description = "Prefix for every resource name, e.g. retailpulse-dev"
  type        = string
}

variable "parameter_prefix" {
  description = "SSM Parameter Store path for connection details, e.g. /retailpulse/dev"
  type        = string
}

variable "alert_email" {
  description = "Email address that receives budget alerts"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for the whole account, in USD"
  type        = number
  default     = 10
}

variable "db_ingress_cidrs" {
  description = "CIDR ranges allowed to reach PostgreSQL on 5432"
  type        = list(string)
}

variable "sftp_ingress_cidrs" {
  description = "CIDR ranges allowed to reach the SFTP server on 22"
  type        = list(string)
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "sftp_instance_type" {
  type    = string
  default = "t4g.nano"
}

variable "schedule_enabled" {
  description = "Start and stop RDS and the SFTP server around the daily window"
  type        = bool
  default     = true
}

variable "window_start_cron" {
  description = "When RDS and SFTP start each day (EventBridge Scheduler cron, UTC)"
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "window_stop_cron" {
  description = "When RDS and SFTP stop each day (EventBridge Scheduler cron, UTC)"
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "carrier_api_source_dir" {
  description = "Folder with the carrier API Lambda code"
  type        = string
}
