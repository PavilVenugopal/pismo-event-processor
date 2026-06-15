# Long-polls SQS and dispatches each message to the router.
# Also handles the SNS notification wrapper LocalStack adds when using SNS→SQS fan-out.
import json
import logging
import signal
import time

import boto3

from src.config import config
from src.models import Event

logger = logging.getLogger(__name__)


class SQSConsumer:
    def __init__(self, on_event):
        self._client = boto3.client(
            "sqs",
            region_name=config.aws_region,
            endpoint_url=config.aws_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        self._on_event = on_event
        self._running = False

    def start(self):
        self._running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
        logger.info("Consumer started, polling SQS...")

        while self._running:
            try:
                response = self._client.receive_message(
                    QueueUrl=config.sqs_queue_url,
                    MaxNumberOfMessages=config.max_messages,
                    WaitTimeSeconds=config.poll_wait_seconds,
                )
                messages = response.get("Messages", [])
                for msg in messages:
                    self._handle(msg)
            except Exception as e:
                logger.error(f"Error polling SQS: {e}")
                time.sleep(2)

        logger.info("Consumer stopped.")

    def _handle(self, msg: dict):
        receipt = msg["ReceiptHandle"]
        try:
            body = json.loads(msg["Body"])

            # SNS wraps the real message in a Notification envelope — unwrap it
            if isinstance(body, dict) and body.get("Type") == "Notification":
                inner = body["Message"]
                # LocalStack sometimes double-encodes the inner message as a string
                if isinstance(inner, str):
                    body = json.loads(inner)
                else:
                    body = inner

            event = Event(**body)
            self._on_event(event)
            self._delete(receipt)
        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            # Leave it in the queue — SQS will redrive to DLQ after maxReceiveCount

    def _delete(self, receipt: str):
        self._client.delete_message(
            QueueUrl=config.sqs_queue_url,
            ReceiptHandle=receipt,
        )

    def _shutdown(self, signum, frame):
        logger.info(f"Signal {signum} received, shutting down...")
        self._running = False
