# Unit tests for the SQS consumer — all boto3 calls are mocked, no AWS needed.
# Main things covered: SNS envelope unwrapping and making sure bad messages aren't deleted.
import json
import unittest
from unittest.mock import MagicMock

from src.consumer import SQSConsumer
from src.models import Event


def make_sqs_message(body: dict) -> dict:
    return {
        "Body": json.dumps(body),
        "ReceiptHandle": "receipt-handle-123",
    }


def make_sns_wrapped_message(inner: dict) -> dict:
    # LocalStack wraps SNS→SQS messages in this envelope
    return {
        "Body": json.dumps({
            "Type": "Notification",
            "Message": json.dumps(inner),
        }),
        "ReceiptHandle": "receipt-handle-456",
    }


class TestSQSConsumer(unittest.TestCase):
    def _make_consumer(self):
        received = []
        consumer = SQSConsumer(on_event=received.append)
        consumer._client = MagicMock()
        return consumer, received

    def test_plain_message_parsed(self):
        consumer, received = self._make_consumer()
        event_data = {
            "event_id": "e1",
            "event_type": "account.created",
            "tenant_id": "t1",
            "timestamp": "2024-01-01T00:00:00",
            "schema_version": "1.0",
            "payload": {"account_id": "a1", "account_type": "checking", "holder_name": "X", "opened_at": "2024-01-01T00:00:00Z"},
        }
        consumer._handle(make_sqs_message(event_data))
        assert len(received) == 1
        assert isinstance(received[0], Event)
        assert received[0].event_id == "e1"

    def test_sns_envelope_unwrapped(self):
        consumer, received = self._make_consumer()
        event_data = {
            "event_id": "e2",
            "event_type": "payment.processed",
            "tenant_id": "t2",
            "timestamp": "2024-01-01T00:00:00",
            "schema_version": "1.0",
            "payload": {"payment_id": "p1"},
        }
        consumer._handle(make_sns_wrapped_message(event_data))
        assert len(received) == 1
        assert received[0].event_id == "e2"

    def test_bad_message_does_not_delete(self):
        consumer, received = self._make_consumer()
        consumer._client.delete_message = MagicMock()
        bad_msg = {"Body": "not-json{{{{", "ReceiptHandle": "r1"}
        consumer._handle(bad_msg)
        # Bad messages stay in the queue so SQS can redrive them
        consumer._client.delete_message.assert_not_called()
        assert len(received) == 0
