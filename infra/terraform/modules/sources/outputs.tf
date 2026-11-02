output "sources_bucket" {
  value = aws_s3_bucket.this["sources"].bucket
}

output "simulator_bucket" {
  value = aws_s3_bucket.this["simulator"].bucket
}

output "postgres_endpoint" {
  value = aws_db_instance.orders.endpoint
}

output "rds_instance_identifier" {
  value = aws_db_instance.orders.identifier
}

output "carrier_api_url" {
  value = "${aws_api_gateway_stage.v1.invoke_url}/shipments"
}

output "shipments_table" {
  value = aws_dynamodb_table.shipments.name
}

output "sftp_instance_id" {
  value = aws_instance.sftp.id
}

output "parameter_prefix" {
  description = "Every connection detail, including secrets, is under this Parameter Store path"
  value       = var.parameter_prefix
}

output "iam_users" {
  value = {
    simulator = aws_iam_user.simulator.name
    pipelines = aws_iam_user.pipelines.name
  }
}
