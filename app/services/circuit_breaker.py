"""Circuit-breaker logic for webhook endpoint delivery.

States
------
CLOSED   → Deliveries proceed normally.
OPEN     → Deliveries are blocked.  Entered when `consecutive_failures`
           reaches `circuit_threshold`.  The circuit stays open for
           `circuit_cooldown_s` seconds.
HALF_OPEN→ Cool-down elapsed.  The next delivery is a probe.  If it
           succeeds the circuit closes; if it fails the circuit reopens.

This module is called from:
  - Lambda handler.py  (after each delivery outcome)
  - FastAPI event router (to block submission when circuit is OPEN)
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from app.models.endpoint import CircuitState

if TYPE_CHECKING:
    from app.models.endpoint import Endpoint

logger = structlog.get_logger(__name__)


def get_effective_state(endpoint: "Endpoint") -> str:
    """Compute the real-time state (handles OPEN → HALF_OPEN transition)."""
    if endpoint.circuit_state != CircuitState.OPEN:
        return endpoint.circuit_state

    if endpoint.circuit_opened_at is None:
        return CircuitState.OPEN

    elapsed = (datetime.now(timezone.utc) - endpoint.circuit_opened_at).total_seconds()
    if elapsed >= endpoint.circuit_cooldown_s:
        return CircuitState.HALF_OPEN

    return CircuitState.OPEN


def record_success(endpoint: "Endpoint") -> None:
    """Reset breaker after a successful delivery."""
    endpoint.consecutive_failures = 0
    endpoint.circuit_state = CircuitState.CLOSED
    endpoint.circuit_opened_at = None
    logger.info("circuit_closed", endpoint_id=str(endpoint.id))


def record_failure(endpoint: "Endpoint") -> None:
    """Increment failure counter and trip the breaker if threshold is reached."""
    endpoint.consecutive_failures += 1

    if endpoint.consecutive_failures >= endpoint.circuit_threshold:
        if endpoint.circuit_state != CircuitState.OPEN:
            endpoint.circuit_state = CircuitState.OPEN
            endpoint.circuit_opened_at = datetime.now(timezone.utc)
            logger.warning(
                "circuit_opened",
                endpoint_id=str(endpoint.id),
                consecutive_failures=endpoint.consecutive_failures,
                cooldown_s=endpoint.circuit_cooldown_s,
            )
    else:
        logger.debug(
            "circuit_failure_recorded",
            endpoint_id=str(endpoint.id),
            consecutive_failures=endpoint.consecutive_failures,
            threshold=endpoint.circuit_threshold,
        )


def is_delivery_allowed(endpoint: "Endpoint") -> tuple[bool, str]:
    """Return (allowed, reason).  Updates state in-place for HALF_OPEN probe."""
    state = get_effective_state(endpoint)

    if state == CircuitState.OPEN:
        return False, "circuit_open"

    if state == CircuitState.HALF_OPEN:
        # Transition to half_open probe – update the persisted state so the
        # Lambda can detect it on the next read
        endpoint.circuit_state = CircuitState.HALF_OPEN
        logger.info("circuit_half_open_probe", endpoint_id=str(endpoint.id))
        return True, "half_open_probe"

    return True, "ok"
