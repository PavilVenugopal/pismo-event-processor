# Writes events to DynamoDB using tenant_id as the partition key.
# Sort key is timestamp#event_id so queries come back in time order per tenant.
import json
import logging
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from src.config import config
from src.models import ProcessedEvent

logger = logging.getLogger(__name__)


def _floats_to_decimal(obj):
    # DynamoDB rejects float types — cheapest fix is a JSON round-trip through Decimal
    return json.loads(json.dumps(obj), parse_float=Decimal)


class DynamoStore:
    def __init__(self):
        self._resource = boto3.resource(
            "dynamodb",
            region_name=config.aws_region,
            endpoint_url=config.aws_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        self._table = self._resource.Table(config.dynamodb_table)

    def save(self, event: ProcessedEvent) -> None:
        item = _floats_to_decimal({
            "tenant_id": event.tenant_id,
            "sort_key": f"{event.timestamp}#{event.event_id}",
            "event_id": event.event_id,
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "payload": event.payload,
            "processed_at": event.processed_at,
            "status": event.status,
        })
        self._table.put_item(Item=item)
        logger.debug(f"Saved event {event.event_id} to DynamoDB")

    def query_by_tenant(self, tenant_id: str) -> list:
        response = self._table.query(
            KeyConditionExpression=Key("tenant_id").eq(tenant_id)
        )
        return response.get("Items", [])
