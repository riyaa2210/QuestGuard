"""HMAC-SHA256 payload signing.

Produces a signature identical in format to GitHub/Stripe webhook signatures:

    X-QueueGuard-Signature: sha256=<hex_digest>

The Lambda delivery handler reads the raw secret from the endpoint row and
calls `sign_payload()` before each HTTP delivery.  Receivers can verify by
computing the same HMAC over the raw request body using the shared secret.
"""

import hashlib
import hmac
import json
from typing import Optional


def sign_payload(payload: dict, secret: str) -> str:
    """Return the `sha256=<hex>` signature for the given payload and secret."""
    body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    digest = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(payload_bytes: bytes, secret: str, signature_header: str) -> bool:
    """Constant-time verification – use this in receiver implementations."""
    expected = "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
