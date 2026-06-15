# Tests that valid events get saved and invalid ones get sent to the DLQ.
# Mocks out the store and SQS client so the routing logic is tested in isolation.
import json
from unittest.mock import MagicMock, patch

import pytest

from src.models import Event
from src.router import EventRouter


def make_event(event_type: str, payload: dict) -> Event:
    return Event(
        event_id="test-id",
        event_type=event_type,
        tenant_id="tenant-1",
        timestamp="2024-01-01T00:00:00",
        payload=payload,
    )


@pytest.fixture
def mock_validator():
    return MagicMock()


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def router(mock_validator, mock_store):
    with patch("src.router.boto3"):
        r = EventRouter(validator=mock_validator, store=mock_store)
    return r


def test_valid_event_saved(router, mock_validator, mock_store):
    mock_validator.validate.return_value = (True, None)
    event = make_event("transaction.authorized", {"amount": 10})
    result = router.route(event)
    assert result == "valid"
    mock_store.save.assert_called_once()
    assert router.stats["valid"] == 1
    assert router.stats["invalid"] == 0


def test_invalid_event_sent_to_dlq(router, mock_validator):
    mock_validator.validate.return_value = (False, "missing field: currency")
    event = make_event("transaction.authorized", {"bad": "data"})
    result = router.route(event)
    assert result == "invalid"
    router._sqs.send_message.assert_called_once()
    assert router.stats["invalid"] == 1
    assert router.stats["valid"] == 0


def test_stats_accumulate(router, mock_validator, mock_store):
    mock_validator.validate.side_effect = [(True, None), (False, "err"), (True, None)]
    for _ in range(3):
        router.route(make_event("x", {}))
    assert router.stats["processed"] == 3
    assert router.stats["valid"] == 2
    assert router.stats["invalid"] == 1
