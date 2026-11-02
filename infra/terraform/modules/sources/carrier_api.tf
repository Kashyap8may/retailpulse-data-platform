# Mock carrier tracking API: DynamoDB holds shipments, a Lambda serves
# GET /shipments?updated_since=&page_token= behind API Gateway with an API key and usage plan.
# A REST API (not an HTTP API) is used because only REST APIs support API keys and usage plans.

resource "aws_dynamodb_table" "shipments" {
  name         = "${local.p}-shipments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "shipment_id"

  attribute {
    name = "shipment_id"
    type = "S"
  }
  attribute {
    name = "updated_day"
    type = "S"
  }
  attribute {
    name = "updated_at"
    type = "S"
  }

  # Incremental pulls query one UTC day of updated_at at a time instead of scanning the table.
  global_secondary_index {
    name            = "by_updated_day"
    hash_key        = "updated_day"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = false
  }
}

data "archive_file" "carrier_api" {
  type        = "zip"
  source_dir  = var.carrier_api_source_dir
  output_path = "${path.module}/.build/carrier_api.zip"
  excludes    = ["__pycache__"]
}

resource "aws_iam_role" "carrier_api" {
  name = "${local.p}-carrier-api"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "carrier_api" {
  name = "read-shipments"
  role = aws_iam_role.carrier_api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:Scan"]
        Resource = [aws_dynamodb_table.shipments.arn, "${aws_dynamodb_table.shipments.arn}/index/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.carrier_api.arn}:*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "carrier_api" {
  name              = "/aws/lambda/${local.p}-carrier-api"
  retention_in_days = 14
}

resource "aws_lambda_function" "carrier_api" {
  function_name    = "${local.p}-carrier-api"
  role             = aws_iam_role.carrier_api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "handler.handler"
  filename         = data.archive_file.carrier_api.output_path
  source_code_hash = data.archive_file.carrier_api.output_base64sha256
  memory_size      = 256
  timeout          = 15

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.shipments.name
      INDEX_NAME = "by_updated_day"
    }
  }

  depends_on = [aws_cloudwatch_log_group.carrier_api]
}

resource "aws_api_gateway_rest_api" "carrier" {
  name        = "${local.p}-carrier-api"
  description = "Mock carrier tracking API for RetailPulse"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "shipments" {
  rest_api_id = aws_api_gateway_rest_api.carrier.id
  parent_id   = aws_api_gateway_rest_api.carrier.root_resource_id
  path_part   = "shipments"
}

resource "aws_api_gateway_method" "get_shipments" {
  rest_api_id      = aws_api_gateway_rest_api.carrier.id
  resource_id      = aws_api_gateway_resource.shipments.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "get_shipments" {
  rest_api_id             = aws_api_gateway_rest_api.carrier.id
  resource_id             = aws_api_gateway_resource.shipments.id
  http_method             = aws_api_gateway_method.get_shipments.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.carrier_api.invoke_arn
}

resource "aws_api_gateway_deployment" "carrier" {
  rest_api_id = aws_api_gateway_rest_api.carrier.id
  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.shipments.id,
      aws_api_gateway_method.get_shipments.id,
      aws_api_gateway_integration.get_shipments.id,
    ]))
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id   = aws_api_gateway_rest_api.carrier.id
  deployment_id = aws_api_gateway_deployment.carrier.id
  stage_name    = "v1"
}

resource "aws_api_gateway_usage_plan" "carrier" {
  name = "${local.p}-carrier-api"
  api_stages {
    api_id = aws_api_gateway_rest_api.carrier.id
    stage  = aws_api_gateway_stage.v1.stage_name
  }
  throttle_settings {
    rate_limit  = 20
    burst_limit = 40
  }
  quota_settings {
    limit  = 100000
    period = "DAY"
  }
}

resource "aws_api_gateway_api_key" "carrier" {
  name = "${local.p}-carrier-api"
}

resource "aws_api_gateway_usage_plan_key" "carrier" {
  key_id        = aws_api_gateway_api_key.carrier.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.carrier.id
}

resource "aws_lambda_permission" "carrier_api" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.carrier_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.carrier.execution_arn}/*/GET/shipments"
}
