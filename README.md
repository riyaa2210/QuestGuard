# QueueGuard

**AI-assisted webhook reliability platform.**  
Register destination endpoints, submit webhook events, and let QueueGuard handle delivery — with automatic retries, exponential backoff, dead-lettering, idempotency, and optional LLM-powered failure explanations.

---

## Architecture

```
Caller ──POST /events/{endpoint_id}──▶ FastAPI (Python)
                                            │
                                       PostgreSQL
                                       (events, attempts)
                                            │
                                       SQS Main Queue
                                            │
                                    Lambda: delivery handler
                                       │              │
                              HTTP POST endpoint    Retry (delay)
                                   200–299?              │
                                    Yes ──▶ mark delivered
                                    No  ──▶ re-enqueue with backoff
                                              │ (after MAX_RETRY_ATTEMPTS)
                                         SQS Dead-Letter Queue
                                              │
                                    Lambda: DLQ handler
                                         mark dead_lettered
                                         AI explanation (optional)
                                              │
                                       CloudWatch Logs
                                       (metrics, alarms)
                                            │
                                    React Dashboard
                                    (view, filter, replay)
```

**Key design decisions:**

- **At-least-once delivery.** Network retries and Lambda retries mean a downstream endpoint _may_ receive a message more than once. QueueGuard never claims exactly-once delivery.
- **Idempotency** is enforced with a PostgreSQL partial unique index on `(endpoint_id, idempotency_key)`. Duplicate submissions return HTTP 200 with the original event — no re-enqueue.
- **Exponential backoff**: 30 s → 60 s → 120 s → 240 s → 480 s (capped at 900 s, the SQS maximum).
- **AI explanations** are entirely optional. Set `OPENAI_API_KEY` in your environment to enable GPT-powered failure summaries on delivery attempts and DLQ events.
- **Local dev mode**: Docker Compose spins up PostgreSQL + LocalStack (SQS emulation). No AWS account needed for local development.

---

## Project Structure

```
queueguard/
├── app/                   FastAPI backend
│   ├── models/            SQLAlchemy ORM models
│   ├── schemas/           Pydantic request/response schemas
│   ├── services/          Business logic (endpoint, event, SQS, idempotency)
│   ├── routers/           FastAPI route handlers
│   ├── config.py          Pydantic Settings (reads .env)
│   ├── database.py        Async SQLAlchemy engine + session dep
│   └── main.py            App factory
├── alembic/               Database migrations
├── lambda/                AWS Lambda handlers
│   ├── handler.py         Delivery processor (SQS → HTTP POST → retry)
│   ├── dlq_handler.py     Dead-letter queue processor
│   ├── ai_explainer.py    Optional LLM failure explainer
│   ├── cloudwatch_logger.py  Structured CloudWatch log emitter
│   └── db.py              Sync SQLAlchemy session for Lambda
├── terraform/             AWS infrastructure as code
│   ├── sqs.tf             Main queue + DLQ
│   ├── lambda.tf          Delivery + DLQ Lambda functions
│   ├── iam.tf             Execution roles
│   └── cloudwatch.tf      Log groups, metric filters, alarms
├── frontend/              React dashboard (Vite + TypeScript)
│   └── src/
│       ├── api/client.ts  Typed API wrapper (axios)
│       ├── pages/         EndpointsPage, EventsPage
│       └── components/    Layout, StatusBadge, Spinner
├── tests/                 pytest test suite
├── scripts/               LocalStack init, Lambda packaging
├── docker-compose.yml     Local dev stack
├── pyproject.toml         Python dependencies
└── .env.example           Environment variable reference
```

---

## Local Development Setup

### Prerequisites

- Docker Desktop (for Compose)
- Python 3.11+
- Node 20+

### 1 — Clone and configure

```bash
git clone https://github.com/your-org/queueguard.git
cd queueguard
cp .env.example .env
# Edit .env if needed; defaults work out of the box with Docker Compose
```

### 2 — Start all services

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** on `localhost:5432`
- **LocalStack** (SQS + CloudWatch emulation) on `localhost:4566`
- **FastAPI** on `http://localhost:8000` (runs migrations on startup)
- **React dev server** on `http://localhost:5173`

### 3 — Run without Docker (backend only)

```bash
# Create a virtual environment
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Start PostgreSQL and LocalStack separately (or adjust DATABASE_URL to point at your own PG)
# Then:
alembic upgrade head
uvicorn app.main:app --reload
```

### 4 — Run tests

```bash
pip install -e ".[dev]"
pytest                        # all tests with coverage
pytest tests/test_events.py   # specific file
pytest -v -k "idempotency"    # specific test
```

---

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/endpoints` | Register a new endpoint |
| `GET` | `/api/v1/endpoints` | List all endpoints |
| `GET` | `/api/v1/endpoints/{id}` | Get a single endpoint |
| `PATCH` | `/api/v1/endpoints/{id}` | Update URL / description / active state |
| `DELETE` | `/api/v1/endpoints/{id}` | Delete endpoint (cascades to events) |

### Events

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/events/{endpoint_id}` | Submit an event |
| `GET` | `/api/v1/events/{endpoint_id}` | List events for an endpoint (paginated) |
| `GET` | `/api/v1/events/detail/{event_id}` | Get event + all delivery attempts |
| `GET` | `/api/v1/events/detail/{event_id}/attempts` | List delivery attempts |
| `POST` | `/api/v1/events/detail/{event_id}/replay` | Re-enqueue a failed/dead-lettered event |

### Interactive docs

`http://localhost:8000/docs`

---

### API Examples

#### Register an endpoint

```bash
curl -s -X POST http://localhost:8000/api/v1/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://webhook.site/your-unique-id",
    "description": "My test hook",
    "event_types": ["order.created", "payment.failed"]
  }' | jq
```

#### Submit a webhook event

```bash
curl -s -X POST http://localhost:8000/api/v1/events/<endpoint_id> \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "order.created",
    "payload": { "order_id": 1234, "amount": 99.99 },
    "idempotency_key": "order-1234-v1"
  }' | jq
```

#### Submit a duplicate (idempotency)

```bash
# Sending the same idempotency_key again returns HTTP 200 + original event
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8000/api/v1/events/<endpoint_id> \
  -H "Content-Type: application/json" \
  -d '{"event_type":"order.created","payload":{},"idempotency_key":"order-1234-v1"}'
# → 200
```

#### View delivery history

```bash
curl "http://localhost:8000/api/v1/events/<endpoint_id>?status=failed&page=1&page_size=20" | jq
```

#### Replay a failed event

```bash
curl -s -X POST http://localhost:8000/api/v1/events/detail/<event_id>/replay | jq
```

---

## AWS Production Deployment

### 1 — Build the Lambda package

```bash
bash scripts/package_lambda.sh
# Outputs: lambda/queueguard_lambda.zip
```

### 2 — Provision infrastructure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Fill in database_url, aws_region, etc.

terraform init
terraform plan
terraform apply
```

Terraform creates:
- SQS main queue + dead-letter queue with redrive policy
- Two Lambda functions (delivery + DLQ processor) with SQS event source mappings
- IAM execution role with least-privilege SQS + CloudWatch permissions
- CloudWatch log groups, metric filters for delivery success/failure, DLQ depth alarm

### 3 — Deploy the API

The FastAPI backend can be deployed to any Python host (ECS, App Runner, EC2, etc.). Set the environment variables from `.env.example` using your hosting platform's secrets/config mechanism. Never store credentials in code or config files.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(local pg)* | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `SYNC_DATABASE_URL` | *(local pg)* | Sync URL for Alembic + Lambda |
| `AWS_REGION` | `us-east-1` | AWS region |
| `SQS_WEBHOOK_QUEUE_URL` | *(localstack)* | Main SQS queue URL |
| `SQS_DLQ_URL` | *(localstack)* | DLQ URL |
| `LOCALSTACK_ENDPOINT` | `http://localhost:4566` | Set to empty in production |
| `MAX_RETRY_ATTEMPTS` | `5` | Max delivery attempts before dead-lettering |
| `INITIAL_RETRY_DELAY_SECONDS` | `30` | First retry delay (doubles each attempt) |
| `DELIVERY_TIMEOUT_SECONDS` | `10` | HTTP delivery timeout |
| `OPENAI_API_KEY` | *(blank)* | Enables AI failure explanations (optional) |
| `SECRET_KEY` | *(change me)* | App secret — use a long random string |

---

## Known Limitations

- **At-least-once, not exactly-once.** Destination endpoints must handle duplicate deliveries gracefully (e.g., by using the `X-QueueGuard-Event` header or their own idempotency check).
- **Lambda cold starts.** The first delivery after a period of inactivity may be slower than usual.
- **SQS delay cap.** SQS `DelaySeconds` is capped at 900 s (15 min). Very long backoff intervals are not possible without a separate scheduler (e.g., EventBridge Scheduler).
- **No HMAC signature validation UI.** Secrets are stored as bcrypt hashes. Signature verification on the delivery path is not yet implemented.
- **SQLite in tests only.** The test suite uses SQLite for speed. A few PostgreSQL-specific features (e.g., the `JSONB` operator) are not tested in isolation.
- **Single-region.** The current Terraform configuration deploys to one AWS region. Multi-region failover is out of scope for this MVP.
- **AI explainer quality.** LLM explanations are best-effort and may be incorrect or generic. Always verify with raw logs.
#   Q u e s t G u a r d  
 