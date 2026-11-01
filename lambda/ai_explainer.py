"""Optional LLM feature – explains webhook delivery failures in plain English.

Reads OPENAI_API_KEY from the environment.  When the key is absent the
function returns None immediately so callers never need to guard against it.
"""

import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_SYSTEM_PROMPT = (
    "You are a webhook reliability expert. "
    "Given a failed HTTP delivery attempt, explain concisely (≤3 sentences) "
    "what went wrong and what the endpoint operator should check. "
    "Be specific and actionable. Do not repeat the raw error text verbatim."
)


def explain_failure(
    *,
    event_type: str,
    endpoint_url: str,
    http_status_code: Optional[int],
    error_detail: Optional[str],
    response_body: Optional[str],
) -> Optional[str]:
    """Return an LLM-generated plain-English explanation, or None if disabled."""
    if not _OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI  # imported lazily so the Lambda cold-start is unaffected

        client = OpenAI(api_key=_OPENAI_API_KEY)

        user_message = (
            f"Event type: {event_type}\n"
            f"Destination URL: {endpoint_url}\n"
            f"HTTP status code: {http_status_code or 'N/A (connection error)'}\n"
            f"Error detail: {error_detail or 'none'}\n"
            f"Response body (first 500 chars): {(response_body or '')[:500]}"
        )

        completion = client.chat.completions.create(
            model=_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        explanation: str = completion.choices[0].message.content.strip()
        logger.info("ai_explanation_generated", event_type=event_type)
        return explanation
    except Exception as exc:  # never let the explainer crash delivery processing
        logger.warning("ai_explainer_failed", error=str(exc))
        return None
