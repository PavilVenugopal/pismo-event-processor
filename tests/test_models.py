# Basic model tests — checks field validation and the defaults Pydantic sets automatically.
# Worth having so we catch breaking changes to the event structure early.
import pytest
from pydantic import ValidationError

from src.models import Event, ProcessedEvent


def test_event_valid():
    e = Event(
        event_id="abc",
        event_type="transaction.authorized",
        tenant_id="t1",
        timestamp="2024-01-01T00:00:00",
        payload={"amount": 10},
    )
    assert e.schema_version == "1.0"


def test_event_missing_required():
    with pytest.raises(ValidationError):
        Event(event_id="x", tenant_id="t1", timestamp="ts", payload={})


def test_processed_event_defaults():
    pe = ProcessedEvent(
        event_id="e1",
        event_type="account.created",
        tenant_id="t1",
        timestamp="2024-01-01T00:00:00",
        schema_version="1.0",
        payload={},
    )
    assert pe.status == "valid"
    assert pe.processed_at is not None


def test_event_model_dump():
    e = Event(
        event_id="e1",
        event_type="payment.processed",
        tenant_id="t2",
        timestamp="2024-01-01T00:00:00",
        payload={"payment_id": "p1"},
    )
    d = e.model_dump()
    assert d["event_id"] == "e1"
    assert "payload" in d
