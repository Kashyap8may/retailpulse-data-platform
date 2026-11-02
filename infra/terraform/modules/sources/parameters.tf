# Connection details for the simulator and the pipelines. Standard Parameter Store tier is free,
# unlike Secrets Manager. Secret values also sit in Terraform state, which is why the state
# bucket is private and encrypted.

locals {
  plain_parameters = {
    "postgres/host"            = aws_db_instance.orders.address
    "postgres/port"            = tostring(aws_db_instance.orders.port)
    "postgres/database"        = aws_db_instance.orders.db_name
    "postgres/username"        = aws_db_instance.orders.username
    "sftp/username"            = "retailpulse"
    "sftp/port"                = "22"
    "carrier_api/url"          = "${aws_api_gateway_stage.v1.invoke_url}/shipments"
    "s3/sources_bucket"        = aws_s3_bucket.this["sources"].bucket
    "s3/simulator_bucket"      = aws_s3_bucket.this["simulator"].bucket
    "dynamodb/shipments_table" = aws_dynamodb_table.shipments.name
    "aws/region"               = local.region
    "rds/instance_identifier"  = aws_db_instance.orders.identifier
    "sftp/instance_id"         = aws_instance.sftp.id
  }
  secret_parameters = {
    "postgres/password"   = random_password.db.result
    "sftp/private_key"    = tls_private_key.sftp.private_key_openssh
    "carrier_api/api_key" = aws_api_gateway_api_key.carrier.value
  }
}

resource "aws_ssm_parameter" "plain" {
  for_each = local.plain_parameters
  name     = "${var.parameter_prefix}/${each.key}"
  type     = "String"
  value    = each.value
}

resource "aws_ssm_parameter" "secret" {
  for_each = local.secret_parameters
  name     = "${var.parameter_prefix}/${each.key}"
  type     = "SecureString"
  value    = each.value
}

# Written by the SFTP instance itself at every boot; Terraform only creates it.
resource "aws_ssm_parameter" "sftp_host" {
  name  = "${var.parameter_prefix}/sftp/host"
  type  = "String"
  value = "pending-first-boot"
  lifecycle {
    ignore_changes = [value]
  }
}
