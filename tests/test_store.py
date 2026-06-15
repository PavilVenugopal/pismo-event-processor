# Tests DynamoDB reads and writes using moto, which intercepts boto3 calls in-process.
# Covers the normal write path and idempotency — duplicate event_ids should be silently skipped.
import boto3
import pytest
from moto import mock_aws

from src.config import config
from src.models import ProcessedEvent
from src.store import DynamoStore


@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")  # point at moto, not localstack


def _make_table():
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName=config.dynamodb_table,
        KeySchema=[
            {"AttributeName": "tenant_id", "KeyType": "HASH"},
            {"AttributeName": "sort_key", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "tenant_id", "AttributeType": "S"},
            {"AttributeName": "sort_key", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _make_event(event_id="e-test-1"):
    return ProcessedEvent(
        event_id=event_id,
        event_type="account.created",
        tenant_id="tenant-x",
        timestamp="2024-06-01T00:00:00",
        schema_version="1.0",
        payload={"account_id": "a1", "account_type": "checking", "holder_name": "Test", "opened_at": "2024-01-01T00:00:00Z"},
    )


@mock_aws
def test_save_and_query(aws_credentials):
    _make_table()
    config.aws_endpoint_url = None
    store = DynamoStore()

    saved = store.save(_make_event())
    assert saved is True

    items = store.query_by_tenant("tenant-x")
    assert len(items) == 1
    assert items[0]["event_id"] == "e-test-1"

    config.aws_endpoint_url = "http://localhost:4566"


@mock_aws
def test_duplicate_event_skipped(aws_credentials):
    # SQS delivers at-least-once — saving the same event_id twice should be a no-op
    _make_table()
    config.aws_endpoint_url = None
    store = DynamoStore()

    first = store.save(_make_event())
    second = store.save(_make_event())  # same event_id

    assert first is True
    assert second is False  # skipped, not an error

    items = store.query_by_tenant("tenant-x")
    assert len(items) == 1  # still only one item in the table

    config.aws_endpoint_url = "http://localhost:4566"
