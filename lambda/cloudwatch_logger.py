"""CloudWatch structured logging helper used by the Lambda functions.

Emits JSON log entries to a dedicated CloudWatch log group so that metrics
filters and dashboards can parse them without a log processor.

Falls back gracefully when the CloudWatch client cannot be reached
(e.g., in unit tests without AWS access).
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
import structlog
from botocore.exceptions import ClientError

LOG_GROUP = os.environ.get("CW_LOG_GROUP", "/queueguard/deliveries")
LOG_STREAM_PREFIX = "lambda"

logger = structlog.get_logger(__name__)

_localstack = os.environ.get("LOCALSTACK_ENDPOINT", "")
_cw_kwargs: dict = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
if _localstack:
    _cw_kwargs["endpoint_url"] = _localstack
    _cw_kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
    _cw_kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")

_cw_client = boto3.client("logs", **_cw_kwargs)
_sequence_tokens: dict[str, Optional[str]] = {}


def _get_log_stream() -> str:
    date = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"{LOG_STREAM_PREFIX}/{date}"


def _ensure_stream(stream_name: str) -> None:
    try:
        _cw_client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=stream_name)
    except _cw_client.exceptions.ResourceAlreadyExistsException:
        pass
    except ClientError as exc:
        logger.warning("cloudwatch_stream_create_failed", error=str(exc))


def emit(level: str, message: str, **fields: Any) -> None:
    """Emit a structured JSON event to CloudWatch Logs.

    The function is best-effort; failures are logged locally but never
    raise exceptions that would affect the main processing path.
    """
    stream_name = _get_log_stream()
    _ensure_stream(stream_name)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        **fields,
    }
    try:
        kwargs: dict[str, Any] = {
            "logGroupName": LOG_GROUP,
            "logStreamName": stream_name,
            "logEvents": [
                {
                    "timestamp": int(time.time() * 1000),
                    "message": json.dumps(entry, default=str),
                }
            ],
        }
        token = _sequence_tokens.get(stream_name)
        if token:
            kwargs["sequenceToken"] = token

        response = _cw_client.put_log_events(**kwargs)
        _sequence_tokens[stream_name] = response.get("nextSequenceToken")
    except ClientError as exc:
        logger.warning("cloudwatch_emit_failed", error=str(exc))
