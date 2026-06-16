# pismo-event-processor

Take-home submission for Pismo's Sr. Consultant Data Engineer challenge.

## Language note

The challenge expresses a preference for Go. I chose Python here because the focus of the role is data engineering and I can demonstrate the design thinking — reactive consumption, schema-driven validation, tenant-aware persistence, DLQ resilience — more fluently in Python. The architecture maps 1:1 to Go: the SQS consumer becomes a goroutine with a channel, the validator stays the same logic with a Go JSON schema library, and DynamoDB access is a straight swap to the AWS SDK for Go. 

## What it does

Events come in via SNS, get fanned out to SQS, and the processor picks them up from there.

```
SNS (events-topic)
       |
       v
SQS (events-queue) --> Processor --> DynamoDB  (valid events)
                                 \-> SQS DLQ   (invalid events)
```

The processor long-polls SQS, validates each payload against a JSON schema, and either writes it to DynamoDB or forwards it to the dead-letter queue. DLQ has `maxReceiveCount=3` so flaky messages get a few attempts before giving up.

Some decisions I made:

- Event envelope: `event_id`, `event_type`, `tenant_id`, `timestamp`, `schema_version`, `payload`
- DynamoDB key: `PK=tenant_id`, `SK=timestamp#event_id` — time-ordered per-tenant reads without a scan
- New event types are schema-only — add a `.json` file to `schemas/`, no code changes
- LocalStack wraps SNS-to-SQS messages in a `{"Type":"Notification","Message":"..."}` envelope; the consumer strips it

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

Sample output:

```
-> Checking prerequisites...
-> Running unit tests...
18 passed in 0.29s
-> Unit tests passed

-> Starting Docker stack...
-> LocalStack is up
-> Infra init complete
-> Running end-to-end tests...

tests/test_e2e.py::test_valid_event_persisted_in_dynamodb PASSED
tests/test_e2e.py::test_invalid_event_routed_to_dlq PASSED

2 passed in 16.32s
-> E2E tests passed

-> DynamoDB -- events table:
  8 item(s) found
  . payment.processed      | tenant=tenant-beta
  . transaction.authorized | tenant=tenant-beta
  . transaction.authorized | tenant=tenant-alpha
  . payment.processed      | tenant=tenant-alpha
  ... and 4 more

-> DLQ -- events-dlq:
  0 message(s) in DLQ

-> All done.
-> Tearing down Docker stack...
```

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

## Design decisions

Producers publish to an SNS topic rather than writing directly to SQS. That way each producer just fires an event and doesn't need to know what happens next — if we wanted to add an audit log or a second downstream processor, it's a new SQS subscription, not a code change in every producer.

I picked SQS over Kafka or Kinesis because the ops overhead isn't worth it here. SQS is managed, has built-in DLQ support, and does everything we need. Kinesis would make more sense if we needed strict ordering or historical replay — neither applies to this flow.

For persistence I went with DynamoDB. The downstream delivery service needs to read events per tenant quickly, and DynamoDB handles that well with `tenant_id` as the partition key. The sort key is `timestamp#event_id` so reads come back in time order automatically. Schema changes in event payloads don't require table migrations either, which matters when you're supporting multiple event types.

Validation is JSON Schema because it keeps the contract out of the code. The schema files in `schemas/` are the source of truth — readable by anyone, not just the people who wrote the processor. Adding a new event type is just adding a file.

SQS is at-least-once, so the same message can show up twice, especially after restarts. The store uses a DynamoDB condition (`attribute_not_exists(event_id)`) on every write so duplicates get silently dropped rather than written twice. It's a small thing but it matters in production.

On the failure side — messages that fail processing are never deleted from SQS. After three failed attempts, SQS moves them to the DLQ automatically. Nothing gets lost, they just sit there until someone fixes the schema or replays them.

## Config

| Variable | Default | Description |
|---|---|---|
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | LocalStack |
| `SQS_QUEUE_URL` | `.../events-queue` | Main queue |
| `DLQ_URL` | `.../events-dlq` | Dead-letter queue |
| `DYNAMODB_TABLE` | `events` | Table name |
| `SCHEMAS_DIR` | `schemas` | Schema file location |
| `POLL_WAIT_SECONDS` | `5` | Long-poll timeout |
