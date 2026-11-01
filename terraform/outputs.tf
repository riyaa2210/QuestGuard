output "events_queue_url" {
  description = "SQS URL for the main webhook events queue"
  value       = aws_sqs_queue.events.url
}

output "dlq_url" {
  description = "SQS URL for the dead-letter queue"
  value       = aws_sqs_queue.dlq.url
}

output "delivery_lambda_arn" {
  description = "ARN of the delivery Lambda function"
  value       = aws_lambda_function.delivery.arn
}

output "dlq_lambda_arn" {
  description = "ARN of the DLQ processor Lambda function"
  value       = aws_lambda_function.dlq_processor.arn
}

output "lambda_role_arn" {
  description = "IAM role ARN attached to the Lambda functions"
  value       = aws_iam_role.lambda_exec.arn
}
