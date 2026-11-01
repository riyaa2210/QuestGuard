"""add circuit breaker, rate limit, schema validation, alert rules, trace columns

Revision ID: 0002
Revises: 0001
Create Date: 2024-06-02 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── endpoints: circuit breaker + rate limit + schema + HMAC secret ────────
    op.add_column("endpoints", sa.Column("secret_raw", sa.String(256), nullable=True))
    op.add_column("endpoints", sa.Column("payload_schema", postgresql.JSONB(), nullable=True))
    op.add_column("endpoints", sa.Column("circuit_state", sa.String(16), nullable=False,
                                          server_default="closed"))
    op.add_column("endpoints", sa.Column("consecutive_failures", sa.Integer(), nullable=False,
                                          server_default="0"))
    op.add_column("endpoints", sa.Column("circuit_opened_at", sa.DateTime(timezone=True),
                                          nullable=True))
    op.add_column("endpoints", sa.Column("circuit_threshold", sa.Integer(), nullable=False,
                                          server_default="5"))
    op.add_column("endpoints", sa.Column("circuit_cooldown_s", sa.Integer(), nullable=False,
                                          server_default="600"))
    op.add_column("endpoints", sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False,
                                          server_default="0"))

    # Drop old bcrypt-hashed secret column (replaced by secret_raw for Lambda signing)
    op.drop_column("endpoints", "secret_hash")

    # ── webhook_events: OTel trace context ────────────────────────────────────
    op.add_column("webhook_events", sa.Column("trace_id", sa.String(64), nullable=True))
    op.add_column("webhook_events", sa.Column("span_id", sa.String(32), nullable=True))
    op.create_index("ix_webhook_events_trace_id", "webhook_events", ["trace_id"])

    # ── alert_rules ───────────────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("failure_rate_threshold", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("min_sample_size", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alert_rules_endpoint_id", "alert_rules", ["endpoint_id"])

    # ── rate_limit_buckets ────────────────────────────────────────────────────
    op.create_table(
        "rate_limit_buckets",
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("bucket_ts", sa.DateTime(timezone=True), nullable=False, primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_table("alert_rules")
    op.drop_index("ix_webhook_events_trace_id", table_name="webhook_events")
    op.drop_column("webhook_events", "trace_id")
    op.drop_column("webhook_events", "span_id")
    op.drop_column("endpoints", "rate_limit_per_minute")
    op.drop_column("endpoints", "circuit_cooldown_s")
    op.drop_column("endpoints", "circuit_threshold")
    op.drop_column("endpoints", "circuit_opened_at")
    op.drop_column("endpoints", "consecutive_failures")
    op.drop_column("endpoints", "circuit_state")
    op.drop_column("endpoints", "payload_schema")
    op.drop_column("endpoints", "secret_raw")
    op.add_column("endpoints", sa.Column("secret_hash", sa.String(256), nullable=True))
