# Wires the consumer, validator, router, and store together and starts the poll loop.
# JSON logging makes it easier to grep and pipe the output when running in Docker.
import logging
import sys

from pythonjsonlogger import jsonlogger

from src.config import config
from src.consumer import SQSConsumer
from src.router import EventRouter
from src.store import DynamoStore
from src.validator import SchemaValidator


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting pismo-event-processor", extra={
        "queue": config.sqs_queue_url,
        "table": config.dynamodb_table,
        "schemas_dir": config.schemas_dir,
    })

    validator = SchemaValidator(schemas_dir=config.schemas_dir)
    store = DynamoStore()
    router = EventRouter(validator=validator, store=store)
    consumer = SQSConsumer(on_event=router.route)

    try:
        consumer.start()
    finally:
        s = router.stats
        logger.info(
            "Shutdown complete",
            extra={"processed": s["processed"], "valid": s["valid"], "invalid": s["invalid"]},
        )


if __name__ == "__main__":
    main()
