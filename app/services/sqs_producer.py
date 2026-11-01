"""SQS producer – enqueues webhook events for async delivery.

In local-dev mode the client points to LocalStack.
In production the boto3 client uses the ambient IAM role; no credentials
are ever stored in code or config files.
"""

import json
import uuid
from typing import Optional

import boto3
import structlog
from botocore.exceptions import ClientError

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def _make_sqs_client():
    kwargs: dict = {"region_name": settings.aws_region}
    if settings.localstack_endpoint:
        kwargs["endpoint_url"] = settings.localstack_endpoint
        # LocalStack accepts any fake creds
        kwargs["aws_access_key_id"] = settings.aws_access_key_id or "test"
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key or "test"
    return boto3.client("sqs", **kwargs)


class SQSProducer:
    """Thin wrapper around the SQS send_message API."""

    def __init__(self):
        self._client = _make_sqs_client()

    def enqueue_event(
        self,
        *,
        event_id: uuid.UUID,
        endpoint_id: uuid.UUID,
        event_type: str,
        payload: dict,
        attempt_number: int = 1,
        delay_seconds: int = 0,
        trace_id: str = "",
        span_id: str = "",
    ) -> Optional[str]:
        """Send a delivery job to SQS.  Returns the SQS message ID on success."""
        message_body = json.dumps(
            {
                "event_id": str(event_id),
                "endpoint_id": str(endpoint_id),
                "event_type": event_type,
                "payload": payload,
                "attempt_number": attempt_number,
                "trace_id": trace_id,
                "span_id": span_id,
            }
        )
        try:
            response = self._client.send_message(
                QueueUrl=settings.sqs_webhook_queue_url,
                MessageBody=message_body,
                DelaySeconds=min(delay_seconds, 900),  # SQS max is 900 s
                MessageAttributes={
                    "event_type": {
                        "DataType": "String",
                        "StringValue": event_type,
                    },
                    "attempt_number": {
                        "DataType": "Number",
                        "StringValue": str(attempt_number),
                    },
                    **({"trace_id": {"DataType": "String", "StringValue": trace_id}} if trace_id else {}),
                },
            )
            message_id: str = response["MessageId"]
            logger.info(
                "sqs_message_sent",
                event_id=str(event_id),
                sqs_message_id=message_id,
                attempt=attempt_number,
                delay_s=delay_seconds,
            )
            return message_id
        except ClientError as exc:
            logger.error(
                "sqs_send_failed",
                event_id=str(event_id),
                error=str(exc),
            )
            return None


# Module-level singleton; replaced in tests via dependency injection
_producer: Optional[SQSProducer] = None


def get_producer() -> SQSProducer:
    global _producer
    if _producer is None:
        _producer = SQSProducer()
    return _producer
