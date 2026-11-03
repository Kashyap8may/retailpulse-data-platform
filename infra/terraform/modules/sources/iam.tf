# Two machine users for Databricks Free Edition, which cannot assume an IAM role in this account.
# Terraform creates no access keys, so none end up in state; M3 creates them straight into a
# Databricks secret scope.
#
#   simulator: publishes each day's data into the sources (and reads the pre-generated year)
#   pipelines: what the owner's bronze jobs use; read-only on the sources, no simulator access

locals {
  parameter_arn = "arn:aws:ssm:${local.region}:${local.account_id}:parameter${var.parameter_prefix}"
  sources_arn   = aws_s3_bucket.this["sources"].arn
  simulator_arn = aws_s3_bucket.this["simulator"].arn

  # Both users may wake the sources up when they run outside the daily window.
  wake_sources = [
    {
      Effect   = "Allow"
      Action   = ["rds:StartDBInstance", "rds:DescribeDBInstances"]
      Resource = aws_db_instance.orders.arn
    },
    {
      Effect   = "Allow"
      Action   = "ec2:StartInstances"
      Resource = aws_instance.sftp.arn
    },
    {
      Effect   = "Allow"
      Action   = "ec2:DescribeInstances"
      Resource = "*"
    },
  ]
}

resource "aws_iam_user" "simulator" {
  name = "${local.p}-databricks-simulator"
}

resource "aws_iam_user_policy" "simulator" {
  name = "publish-to-sources"
  user = aws_iam_user.simulator.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [local.sources_arn, local.simulator_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${local.sources_arn}/*", "${local.simulator_arn}/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:BatchWriteItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:GetItem", "dynamodb:DescribeTable",
        ]
        Resource = aws_dynamodb_table.shipments.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = ["${local.parameter_arn}", "${local.parameter_arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["rds:StopDBInstance"]
        Resource = aws_db_instance.orders.arn
      },
      {
        Effect   = "Allow"
        Action   = "ec2:StopInstances"
        Resource = aws_instance.sftp.arn
      },
    ], local.wake_sources)
  })
}

resource "aws_iam_user" "pipelines" {
  name = "${local.p}-databricks-pipelines"
}

resource "aws_iam_user_policy" "pipelines" {
  name = "read-sources"
  user = aws_iam_user.pipelines.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = local.sources_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${local.sources_arn}/*"
      },
      {
        # An allow-list instead of the whole path: the pipelines must not read the admin password
        # or learn the simulator bucket, and a path-level grant would expose both.
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [for name in local.pipeline_parameters : "${local.parameter_arn}/${name}"]
      },
    ], local.wake_sources)
  })
}

locals {
  pipeline_parameters = [
    "aws/region",
    "postgres/host", "postgres/port", "postgres/database", "postgres/reader_username", "postgres/reader_password",
    "carrier_api/url", "carrier_api/api_key",
    "s3/sources_bucket",
    "sftp/host", "sftp/port", "sftp/username", "sftp/private_key",
    "rds/instance_identifier", "sftp/instance_id",
  ]
}
