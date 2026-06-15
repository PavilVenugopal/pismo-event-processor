# pismo-event-processor

Take-home submission for Pismo's Sr. Consultant Data Engineer challenge.

## Language note

The challenge expresses a preference for Go. I chose Python here because the focus of the role is data engineering and I can demonstrate the design thinking — reactive consumption, schema-driven validation, tenant-aware persistence, DLQ resilience — more fluently in Python. The architecture maps 1:1 to Go: the SQS consumer becomes a goroutine with a channel, the validator stays the same logic with a Go JSON schema library, and DynamoDB access is a straight swap to the AWS SDK for Go. Happy to walk through a Go version or pair on it if that would be useful.

## What it does

Events come in via SNS, get fanned out to SQS, and the processor picks them up from there.

```
SNS (events-topic)
       │
       ▼
SQS (events-queue) ──► Processor ──► DynamoDB  (valid events)
                                 └──► SQS DLQ   (invalid events)
```

The processor long-polls SQS, validates each payload against a JSON schema, and either writes it to DynamoDB or forwards it to the dead-letter queue. DLQ has `maxReceiveCount=3` so flaky messages get a few attempts before giving up.

Some decisions I made:

- Event envelope: `event_id`, `event_type`, `tenant_id`, `timestamp`, `schema_version`, `payload`
- DynamoDB key: `PK=tenant_id`, `SK=timestamp#event_id` — time-ordered per-tenant reads without a scan
- New event types are schema-only — add a `.json` file to `schemas/`, no code changes
- LocalStack wraps SNS→SQS in a `{"Type":"Notification","Message":"..."}` envelope; the consumer strips it

## Layout

```
src/
  config.py        env vars with LocalStack defaults
  models.py        Pydantic v2 event models
  validator.py     JSON schema validation
  consumer.py      SQS long-polling + SNS envelope handling
  router.py        routes to DynamoDB or DLQ
  store.py         DynamoDB writes
  processor.py     entry point, wires everything together
schemas/
  transaction.authorized.json
  account.created.json
  payment.processed.json
producer/
  cli.py           one-shot publisher: --type / --tenant / --count
  auto_producer.py Docker service, publishes every 3s (every 10th is intentionally bad)
scripts/
  init_infra.py    creates SNS/SQS/DynamoDB resources in LocalStack
tests/
  test_*.py        unit tests (moto/mocks, no real AWS)
  test_e2e.py      integration tests (needs LocalStack running)
```

## Running locally

Needs Docker and Docker Compose. No real AWS account.

```bash
make up        # spins up LocalStack, bootstraps infra, starts processor + auto-producer
make logs      # tail processor output (give it ~15s to get going)
make scan-db   # dump DynamoDB — valid events land here
make scan-dlq  # dump the DLQ — every 10th auto-producer event ends up here
make down      # tear everything down and remove volumes
```

The processor outputs structured JSON logs:

```
processor | {"message": "Starting pismo-event-processor", ...}
processor | {"message": "[VALID] account.created id=... tenant=tenant-alpha", ...}
processor | {"message": "[INVALID] transaction.authorized id=... reason=...", ...}
```

## Tests

Unit tests don't need Docker:

```bash
pip install -r requirements-dev.txt
make test-unit
# or if pytest isn't on PATH:
python3 -m pytest tests/ --ignore=tests/test_e2e.py --ignore=tests/test_store.py -v
```

For end-to-end (needs the stack running):

```bash
make up && sleep 15 && make test-e2e
```

Or just run `./run_e2e.sh` — it handles everything and tears down after.

## Publishing events manually

After `make up`, you can push your own events. LocalStack doesn't care about credentials:

```bash
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1 AWS_ENDPOINT_URL=http://localhost:4566

python3 -m producer.cli --type account.created --tenant acme --count 3
python3 -m producer.cli --type transaction.authorized --tenant acme --count 1
```

Then `make scan-db` to see them in DynamoDB.

## Troubleshooting

`scan-db` / `scan-dlq` need the AWS CLI installed (`brew install awscli` on Mac). Credentials don't matter — they point at localhost.

If the processor exits immediately after `make up`, check `docker-compose logs infra-init`. It runs first to create the queues and table; if it fails, the processor has nothing to connect to.

Port 4566 busy? `docker ps | grep localstack` — you probably have another instance running.

## Config

| Variable | Default | Description |
|---|---|---|
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack |
| `SQS_QUEUE_URL` | `.../events-queue` | Main queue |
| `DLQ_URL` | `.../events-dlq` | Dead-letter queue |
| `DYNAMODB_TABLE` | `events` | Table name |
| `SCHEMAS_DIR` | `schemas` | Schema file location |
| `POLL_WAIT_SECONDS` | `5` | Long-poll timeout |
