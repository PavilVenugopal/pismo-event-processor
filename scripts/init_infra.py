# Creates the SNS topic, SQS queues, and DynamoDB table in LocalStack at container startup.
# Exits 0 when done so the processor and producer can declare a dependency on this in docker-compose.
import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

ENDPOINT = "http://localstack:4566"
REGION = "us-east-1"

BOTO = dict(
    region_name=REGION,
    endpoint_url=ENDPOINT,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)


def wait_for_localstack():
    import urllib.request
    url = "http://localstack:4566/_localstack/health"
    for i in range(30):
        try:
            urllib.request.urlopen(url, timeout=2)
            print("LocalStack is up.")
            return
        except Exception:
            print(f"Waiting for LocalStack... ({i+1}/30)")
            time.sleep(2)
    print("LocalStack never became ready.", file=sys.stderr)
    sys.exit(1)


def create_queues(sqs):
    # DLQ has to exist before the main queue so we can set the redrive policy
    try:
        sqs.create_queue(QueueName="events-dlq")
        print("Created events-dlq")
    except ClientError as e:
        if "QueueAlreadyExists" in str(e):
            print("events-dlq already exists")
        else:
            raise

    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=f"{ENDPOINT}/000000000000/events-dlq",
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    redrive = json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"})
    try:
        sqs.create_queue(
            QueueName="events-queue",
            Attributes={"RedrivePolicy": redrive},
        )
        print("Created events-queue")
    except ClientError as e:
        if "QueueAlreadyExists" in str(e):
            print("events-queue already exists")
        else:
            raise

    return dlq_arn


def create_topic_and_subscribe(sns, sqs):
    topic_arn = sns.create_topic(Name="events-topic")["TopicArn"]
    print(f"SNS topic: {topic_arn}")

    queue_arn = sqs.get_queue_attributes(
        QueueUrl=f"{ENDPOINT}/000000000000/events-queue",
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]

    subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn).get("Subscriptions", [])
    if any(s["Endpoint"] == queue_arn for s in subs):
        print("Subscription already exists")
    else:
        sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)
        print("Subscribed events-queue to events-topic")


def create_table(ddb):
    try:
        ddb.create_table(
            TableName="events",
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "sort_key", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "tenant_id", "AttributeType": "S"},
                {"AttributeName": "sort_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print("Created DynamoDB table: events")
    except ClientError as e:
        if "ResourceInUseException" in str(e):
            print("Table already exists")
        else:
            raise


def main():
    wait_for_localstack()

    sqs = boto3.client("sqs", **BOTO)
    sns = boto3.client("sns", **BOTO)
    ddb = boto3.client("dynamodb", **BOTO)

    create_queues(sqs)
    create_topic_and_subscribe(sns, sqs)
    create_table(ddb)

    print("Done.")


if __name__ == "__main__":
    main()
