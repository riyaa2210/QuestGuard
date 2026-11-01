variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment tag (e.g. staging, production)"
  type        = string
  default     = "production"
}

variable "database_url" {
  description = "Synchronous PostgreSQL connection URL for the Lambda functions"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for the AI error explainer (leave blank to disable)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "max_retry_attempts" {
  description = "Maximum number of delivery retries before dead-lettering"
  type        = number
  default     = 5
}

variable "initial_retry_delay_seconds" {
  description = "First-retry delay in seconds (doubles with each attempt)"
  type        = number
  default     = 30
}

variable "delivery_timeout_seconds" {
  description = "HTTP delivery timeout in seconds"
  type        = number
  default     = 10
}

variable "lambda_zip_path" {
  description = "Path to the Lambda deployment zip (built by scripts/package_lambda.sh)"
  type        = string
  default     = "../lambda/queueguard_lambda.zip"
}
