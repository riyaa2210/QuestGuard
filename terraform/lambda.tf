# ── Shared Lambda environment ─────────────────────────────────────────────────
locals {
  lambda_env = {
    SYNC_DATABASE_URL           = var.database_url
    SQS_WEBHOOK_QUEUE_URL       = aws_sqs_queue.events.url
    SQS_DLQ_URL                 = aws_sqs_queue.dlq.url
    AWS_REGION_NAME             = var.aws_region
    MAX_RETRY_ATTEMPTS          = tostring(var.max_retry_attempts)
    INITIAL_RETRY_DELAY_SECONDS = tostring(var.initial_retry_delay_seconds)
    DELIVERY_TIMEOUT_SECONDS    = tostring(var.delivery_timeout_seconds)
    OPENAI_API_KEY              = var.openai_api_key
    CW_LOG_GROUP                = "/queueguard/deliveries"
    LOCALSTACK_ENDPOINT         = "" # empty = real AWS
  }
}

# ── Delivery Lambda ────────────────────────────────────────────────────────────
resource "aws_lambda_function" "delivery" {
  function_name    = "queueguard-delivery-${var.environment}"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  memory_size      = 256

  environment {
    variables = local.lambda_env
  }

  tags = { Environment = var.environment, Service = "queueguard" }
}

resource "aws_lambda_event_source_mapping" "delivery_sqs" {
  event_source_arn                   = aws_sqs_queue.events.arn
  function_name                      = aws_lambda_function.delivery.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

# ── DLQ Lambda ────────────────────────────────────────────────────────────────
resource "aws_lambda_function" "dlq_processor" {
  function_name    = "queueguard-dlq-${var.environment}"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  handler          = "dlq_handler.lambda_handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  memory_size      = 256

  environment {
    variables = local.lambda_env
  }

  tags = { Environment = var.environment, Service = "queueguard" }
}

resource "aws_lambda_event_source_mapping" "dlq_sqs" {
  event_source_arn        = aws_sqs_queue.dlq.arn
  function_name           = aws_lambda_function.dlq_processor.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}
