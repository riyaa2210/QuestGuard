# ── Dead-Letter Queue ──────────────────────────────────────────────────────────
resource "aws_sqs_queue" "dlq" {
  name                       = "queueguard-events-dlq-${var.environment}"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 60

  tags = { Environment = var.environment, Service = "queueguard" }
}

# ── Main Webhook Events Queue ──────────────────────────────────────────────────
resource "aws_sqs_queue" "events" {
  name                       = "queueguard-events-${var.environment}"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400 # 1 day

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_retry_attempts
  })

  tags = { Environment = var.environment, Service = "queueguard" }
}

# Allow the Lambda execution role to read/write both queues
resource "aws_sqs_queue_policy" "events_policy" {
  queue_url = aws_sqs_queue.events.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.lambda_exec.arn }
      Action    = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
      Resource  = aws_sqs_queue.events.arn
    }]
  })
}

resource "aws_sqs_queue_policy" "dlq_policy" {
  queue_url = aws_sqs_queue.dlq.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.lambda_exec.arn }
      Action    = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
      Resource  = aws_sqs_queue.dlq.arn
    }]
  })
}
