# RDS and the SFTP server run only during a daily window, which is most of the cost saving.
# The simulator publishes and the pipelines pull inside that window; anything outside it can
# start the sources itself (see `make sources-up`). Stopping daily also avoids RDS restarting
# on its own after seven days stopped.

resource "aws_iam_role" "scheduler" {
  name = "${local.p}-source-window"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "start-stop-sources"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["rds:StartDBInstance", "rds:StopDBInstance"]
        Resource = aws_db_instance.orders.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:StartInstances", "ec2:StopInstances"]
        Resource = aws_instance.sftp.arn
      },
    ]
  })
}

locals {
  window_actions = {
    rds-start = {
      cron   = var.window_start_cron
      target = "arn:aws:scheduler:::aws-sdk:rds:startDBInstance"
      input  = { DbInstanceIdentifier = aws_db_instance.orders.identifier }
    }
    rds-stop = {
      cron   = var.window_stop_cron
      target = "arn:aws:scheduler:::aws-sdk:rds:stopDBInstance"
      input  = { DbInstanceIdentifier = aws_db_instance.orders.identifier }
    }
    sftp-start = {
      cron   = var.window_start_cron
      target = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
      input  = { InstanceIds = [aws_instance.sftp.id] }
    }
    sftp-stop = {
      cron   = var.window_stop_cron
      target = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
      input  = { InstanceIds = [aws_instance.sftp.id] }
    }
  }
}

resource "aws_scheduler_schedule" "window" {
  for_each                     = local.window_actions
  name                         = "${local.p}-${each.key}"
  schedule_expression          = each.value.cron
  schedule_expression_timezone = "UTC"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = each.value.target
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(each.value.input)
    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
