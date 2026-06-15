# Tests the schema validator against known-good and known-bad payloads for each event type.
# Reads from the real schemas/ directory so these also catch mistakes in the schema files themselves.
import pytest

from src.models import Event
from src.validator import SchemaValidator

SCHEMAS_DIR = "schemas"


def make_event(event_type: str, payload: dict) -> Event:
    return Event(
        event_id="test-id",
        event_type=event_type,
        tenant_id="tenant-1",
        timestamp="2024-01-01T00:00:00",
        payload=payload,
    )


@pytest.fixture
def validator():
    return SchemaValidator(SCHEMAS_DIR)


def test_valid_transaction(validator):
    event = make_event("transaction.authorized", {
        "transaction_id": "txn-001",
        "account_id": "acc-001",
        "amount": 100.0,
        "currency": "BRL",
        "holder_name": "Maria",
        "mcc": "5411",
    })
    ok, err = validator.validate(event)
    assert ok is True
    assert err is None


def test_invalid_transaction_missing_field(validator):
    event = make_event("transaction.authorized", {
        "transaction_id": "txn-002",
        "amount": 50.0,
        # missing currency, holder_name, mcc, account_id
    })
    ok, err = validator.validate(event)
    assert ok is False
    assert err is not None


def test_invalid_currency_format(validator):
    event = make_event("transaction.authorized", {
        "transaction_id": "txn-003",
        "account_id": "acc-001",
        "amount": 10.0,
        "currency": "br",  # must be 3 uppercase letters
        "holder_name": "Test",
        "mcc": "1234",
    })
    ok, err = validator.validate(event)
    assert ok is False


def test_valid_account_created(validator):
    event = make_event("account.created", {
        "account_id": "acc-001",
        "account_type": "checking",
        "holder_name": "João",
        "opened_at": "2024-01-01T00:00:00Z",
    })
    ok, err = validator.validate(event)
    assert ok is True


def test_invalid_account_type(validator):
    event = make_event("account.created", {
        "account_id": "acc-001",
        "account_type": "bitcoin",  # not in enum
        "holder_name": "Test",
        "opened_at": "2024-01-01T00:00:00Z",
    })
    ok, err = validator.validate(event)
    assert ok is False


def test_valid_payment(validator):
    event = make_event("payment.processed", {
        "payment_id": "pay-001",
        "from_account": "acc-001",
        "to_account": "acc-002",
        "amount": 200.0,
        "currency": "USD",
        "method": "pix",
    })
    ok, err = validator.validate(event)
    assert ok is True


def test_payment_zero_amount_invalid(validator):
    event = make_event("payment.processed", {
        "payment_id": "pay-002",
        "from_account": "acc-001",
        "to_account": "acc-002",
        "amount": 0,  # schema requires > 0
        "currency": "BRL",
        "method": "ted",
    })
    ok, err = validator.validate(event)
    assert ok is False


def test_unknown_event_type(validator):
    event = make_event("unknown.event", {"foo": "bar"})
    ok, err = validator.validate(event)
    assert ok is False
    assert "No schema found" in err
