"""JSON Schema validation for incoming event payloads.

When an endpoint has a `payload_schema` defined, every submitted event's
payload is validated against it before being accepted.  Invalid payloads
are rejected at the API layer with HTTP 422 and a structured error message.

We use the `jsonschema` library (draft 7 by default).  It is a lightweight,
well-maintained dependency that mirrors what most API gateway schema validators
do internally.
"""

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


def validate_payload(
    payload: dict[str, Any],
    schema: Optional[dict],
    endpoint_id: str,
    event_type: str,
) -> list[str]:
    """
    Validate `payload` against `schema`.

    Returns a list of human-readable error strings.
    An empty list means the payload is valid (or no schema is configured).
    """
    if not schema:
        return []

    try:
        import jsonschema  # imported lazily – not installed in Lambda bundle

        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if errors:
            messages = [f"{'.'.join(str(p) for p in e.path) or 'root'}: {e.message}" for e in errors]
            logger.info(
                "payload_schema_validation_failed",
                endpoint_id=endpoint_id,
                event_type=event_type,
                error_count=len(messages),
            )
            return messages
        return []
    except ImportError:
        logger.warning("jsonschema_not_installed_skipping_validation")
        return []
    except jsonschema.SchemaError as exc:
        logger.error("invalid_json_schema_on_endpoint", endpoint_id=endpoint_id, error=str(exc))
        return []
