# Takes a validated event and decides where it goes — DynamoDB if valid, DLQ if not.
# Keeps a running tally of processed/valid/invalid for the shutdown log.
import json
import logging

import boto3

from src.config import config
from src.models import Event, ProcessedEvent
from src.store import DynamoStore
from src.validator import SchemaValidator

logger = logging.getLogger(__name__)


class EventRouter:
    def __init__(self, validator: SchemaValidator, store: DynamoStore):
        self.validator = validator
        self.store = store
        self._sqs = boto3.client(
            "sqs",
            region_name=config.aws_region,
            endpoint_url=config.aws_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        self.stats = {"processed": 0, "valid": 0, "invalid": 0}

    def route(self, event: Event) -> str:
        # returns 'valid' or 'invalid'
        self.stats["processed"] += 1
        is_valid, error = self.validator.validate(event)

        if is_valid:
            processed = ProcessedEvent(**event.model_dump())
            self.store.save(processed)
            self.stats["valid"] += 1
            logger.info(f"[VALID] {event.event_type} id={event.event_id} tenant={event.tenant_id}")
            return "valid"
        else:
            self._send_to_dlq(event, error)
            self.stats["invalid"] += 1
            logger.warning(f"[INVALID] {event.event_type} id={event.event_id} reason={error}")
            return "invalid"

    def _send_to_dlq(self, event: Event, reason) -> None:
        body = {
            "event": event.model_dump(),
            "validation_error": reason,
        }
        self._sqs.send_message(
            QueueUrl=config.dlq_url,
            MessageBody=json.dumps(body),
        )
