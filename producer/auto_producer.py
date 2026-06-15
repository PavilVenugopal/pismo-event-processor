# Runs as a Docker service and sends a mix of valid and invalid events every 3 seconds.
# Every 10th event is intentionally broken to make sure DLQ routing actually works.
import json
import logging
import random
import sys
import time
import uuid
from datetime import datetime

import boto3

sys.path.insert(0, ".")

from src.config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TENANTS = ["tenant-alpha", "tenant-beta", "tenant-gamma"]

VALID_EVENTS = [
    ("transaction.authorized", {
        "transaction_id": "txn-{uid}",
        "account_id": "acc-001",
        "amount": 99.99,
        "currency": "BRL",
        "holder_name": "Ana Costa",
        "mcc": "5812",
    }),
    ("account.created", {
        "account_id": "acc-{uid}",
        "account_type": "savings",
        "holder_name": "Carlos Lima",
        "opened_at": "2024-03-01T08:00:00Z",
    }),
    ("payment.processed", {
        "payment_id": "pay-{uid}",
        "from_account": "acc-100",
        "to_account": "acc-200",
        "amount": 1200.00,
        "currency": "USD",
        "method": "ted",
    }),
]

# Missing required fields and a negative amount — should always fail validation
INVALID_EVENT = ("transaction.authorized", {"amount": -5, "currency": "xx"})


def make_event(event_type: str, payload_template: dict, tenant: str) -> dict:
    uid = uuid.uuid4().hex[:8]
    payload = json.loads(json.dumps(payload_template).replace("{uid}", uid))
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "tenant_id": tenant,
        "timestamp": datetime.utcnow().isoformat(),
        "schema_version": "1.0",
        "payload": payload,
    }


def main():
    topic_arn = f"arn:aws:sns:{config.aws_region}:000000000000:events-topic"
    client = boto3.client(
        "sns",
        region_name=config.aws_region,
        endpoint_url=config.aws_endpoint_url,
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
    )

    logger.info(f"Auto-producer started, publishing to {topic_arn} every 3s")
    counter = 0

    while True:
        counter += 1
        tenant = random.choice(TENANTS)

        if counter % 10 == 0:
            event_type, payload = INVALID_EVENT
        else:
            event_type, payload = random.choice(VALID_EVENTS)

        event = make_event(event_type, payload, tenant)
        try:
            client.publish(TopicArn=topic_arn, Message=json.dumps(event))
            logger.info(f"Published #{counter} type={event_type} tenant={tenant} id={event['event_id']}")
        except Exception as e:
            logger.error(f"Failed to publish: {e}")

        time.sleep(3)


if __name__ == "__main__":
    main()
