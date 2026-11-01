#!/bin/bash
# Runs inside LocalStack on startup to provision SQS queues

set -e

echo "==> Creating SQS queues..."

awslocal sqs create-queue \
  --queue-name queueguard-events-dlq \
  --attributes '{"MessageRetentionPeriod":"1209600"}'

DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/queueguard-events-dlq \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)

awslocal sqs create-queue \
  --queue-name queueguard-events \
  --attributes "{
    \"VisibilityTimeout\": \"60\",
    \"MessageRetentionPeriod\": \"86400\",
    \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"
  }"

echo "==> SQS queues ready."

# CloudWatch log group
awslocal logs create-log-group --log-group-name /queueguard/deliveries 2>/dev/null || true

echo "==> LocalStack init complete."
