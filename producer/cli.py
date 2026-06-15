# Publishes test events to SNS from the command line.
# Usage: python -m producer.cli --type account.created --tenant tenant-1 --count 5
import argparse
import json
import sys
import uuid
from datetime import datetime

import boto3

sys.path.insert(0, ".")

from src.config import config

SAMPLE_PAYLOADS = {
    "transaction.authorized": {
        "transaction_id": "txn-{uid}",
        "account_id": "acc-001",
        "amount": 150.00,
        "currency": "BRL",
        "holder_name": "Maria Silva",
        "mcc": "5411",
    },
    "account.created": {
        "account_id": "acc-{uid}",
        "account_type": "checking",
        "holder_name": "João Santos",
        "opened_at": "2024-01-15T10:30:00Z",
    },
    "payment.processed": {
        "payment_id": "pay-{uid}",
        "from_account": "acc-001",
        "to_account": "acc-002",
        "amount": 500.00,
        "currency": "BRL",
        "method": "pix",
    },
}


def build_event(event_type: str, tenant_id: str) -> dict:
    uid = uuid.uuid4().hex[:8]
    payload = json.loads(
        json.dumps(SAMPLE_PAYLOADS.get(event_type, {})).replace("{uid}", uid)
    )
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "tenant_id": tenant_id,
        "timestamp": datetime.utcnow().isoformat(),
        "schema_version": "1.0",
        "payload": payload,
    }


def publish(event_type: str, tenant_id: str, count: int):
    client = boto3.client(
        "sns",
        region_name=config.aws_region,
        endpoint_url=config.aws_endpoint_url,
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
    )
    topic_arn = f"arn:aws:sns:{config.aws_region}:000000000000:events-topic"

    for i in range(count):
        event = build_event(event_type, tenant_id)
        client.publish(TopicArn=topic_arn, Message=json.dumps(event))
        print(f"Published [{i+1}/{count}] event_id={event['event_id']} type={event_type}")


def main():
    parser = argparse.ArgumentParser(description="Publish events to SNS")
    parser.add_argument("--type", required=True, choices=list(SAMPLE_PAYLOADS.keys()), dest="event_type")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()
    publish(args.event_type, args.tenant, args.count)


if __name__ == "__main__":
    main()
