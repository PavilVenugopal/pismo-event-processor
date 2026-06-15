# Reads environment variables and falls back to LocalStack defaults for local dev.
# Nothing fancy here — just a single config object everything else imports.
import os


class Config:
    aws_region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    aws_endpoint_url: str = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "test")
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "test")

    sqs_queue_url: str = os.getenv(
        "SQS_QUEUE_URL",
        "http://localhost:4566/000000000000/events-queue",
    )
    dlq_url: str = os.getenv(
        "DLQ_URL",
        "http://localhost:4566/000000000000/events-dlq",
    )
    dynamodb_table: str = os.getenv("DYNAMODB_TABLE", "events")
    schemas_dir: str = os.getenv("SCHEMAS_DIR", "schemas")

    poll_wait_seconds: int = int(os.getenv("POLL_WAIT_SECONDS", "5"))
    max_messages: int = int(os.getenv("MAX_MESSAGES", "10"))


config = Config()
