# End-to-end tests that run against a live LocalStack instance.
# Skipped by default — set RUN_INTEGRATION=1 to enable them.
import json
import os
import time
import uuid

import boto3
import pytest

RUN_INTEGRATION = os.getenv("RUN_INTEGRATION", "0") == "1"
pytestmark = pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_INTEGRATION=1 to run")

ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"
TOPIC_ARN = f"arn:aws:sns:{REGION}:000000000000:events-topic"
QUEUE_URL = f"{ENDPOINT}/000000000000/events-queue"
DLQ_URL = f"{ENDPOINT}/000000000000/events-dlq"
TABLE = "events"

BOTO_KWARGS = dict(
    region_name=REGION,
    endpoint_url=ENDPOINT,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)


@pytest.fixture(scope="module")
def sns():
    return boto3.client("sns", **BOTO_KWARGS)


@pytest.fixture(scope="module")
def sqs():
    return boto3.client("sqs", **BOTO_KWARGS)


@pytest.fixture(scope="module")
def ddb():
    return boto3.resource("dynamodb", **BOTO_KWARGS)


def publish_event(sns_client, event_type: str, tenant_id: str, payload: dict) -> str:
    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
        "timestamp": "2024-06-01T12:00:00",
        "schema_version": "1.0",
        "payload": payload,
    }
    sns_client.publish(TopicArn=TOPIC_ARN, Message=json.dumps(event))
    return event_id


def test_valid_event_persisted_in_dynamodb(sns, ddb):
    tenant = f"e2e-tenant-{uuid.uuid4().hex[:6]}"
    event_id = publish_event(sns, "account.created", tenant, {
        "account_id": "acc-e2e",
        "account_type": "credit",
        "holder_name": "E2E Test",
        "opened_at": "2024-01-01T00:00:00Z",
    })
    time.sleep(8)

    table = ddb.Table(TABLE)
    resp = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("tenant_id").eq(tenant)
    )
    ids = [item["event_id"] for item in resp.get("Items", [])]
    assert event_id in ids, f"event {event_id} not found in DynamoDB; got: {ids}"


def test_invalid_event_routed_to_dlq(sns, sqs):
    tenant = f"e2e-invalid-{uuid.uuid4().hex[:6]}"
    event_id = publish_event(sns, "transaction.authorized", tenant, {
        "amount": -999,  # negative amount, missing required fields
    })
    time.sleep(8)

    resp = sqs.receive_message(QueueUrl=DLQ_URL, MaxNumberOfMessages=10, WaitTimeSeconds=5)
    messages = resp.get("Messages", [])
    dlq_event_ids = []
    for msg in messages:
        body = json.loads(msg["Body"])
        dlq_event_ids.append(body.get("event", {}).get("event_id"))

    assert event_id in dlq_event_ids, f"event {event_id} not in DLQ; got: {dlq_event_ids}"
