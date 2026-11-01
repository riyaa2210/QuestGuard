# ── CloudWatch Log Groups ──────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "delivery_logs" {
  name              = "/queueguard/deliveries"
  retention_in_days = 30
  tags              = { Environment = var.environment }
}

resource "aws_cloudwatch_log_group" "lambda_delivery" {
  name              = "/aws/lambda/queueguard-delivery-${var.environment}"
  retention_in_days = 14
  tags              = { Environment = var.environment }
}

resource "aws_cloudwatch_log_group" "lambda_dlq" {
  name              = "/aws/lambda/queueguard-dlq-${var.environment}"
  retention_in_days = 14
  tags              = { Environment = var.environment }
}

# ── Metric Filters ─────────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_metric_filter" "delivery_success" {
  name           = "queueguard-delivery-success"
  pattern        = "{ $.message = \"delivery_success\" }"
  log_group_name = aws_cloudwatch_log_group.delivery_logs.name

  metric_transformation {
    name      = "DeliverySuccess"
    namespace = "QueueGuard"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "delivery_failed" {
  name           = "queueguard-delivery-failed"
  pattern        = "{ $.message = \"delivery_failed_retrying\" }"
  log_group_name = aws_cloudwatch_log_group.delivery_logs.name

  metric_transformation {
    name      = "DeliveryFailed"
    namespace = "QueueGuard"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "event_dead_lettered" {
  name           = "queueguard-dead-lettered"
  pattern        = "{ $.message = \"event_dead_lettered\" }"
  log_group_name = aws_cloudwatch_log_group.delivery_logs.name

  metric_transformation {
    name      = "EventsDeadLettered"
    namespace = "QueueGuard"
    value     = "1"
  }
}

# ── Alarms ─────────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "high_dlq_depth" {
  alarm_name          = "queueguard-high-dlq-depth-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "More than 10 messages are sitting in the DLQ"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "queueguard-lambda-errors-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Delivery Lambda is throwing unhandled errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.delivery.function_name
  }
}
