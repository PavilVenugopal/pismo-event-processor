#!/bin/bash
set -e

ENDPOINT="http://localstack:4566"
REGION="us-east-1"
AWS_CMD="aws --endpoint-url=$ENDPOINT --region=$REGION"

echo "Waiting for LocalStack to be ready..."
until $AWS_CMD sqs list-queues > /dev/null 2>&1; do
  sleep 1
done
echo "LocalStack is ready."

echo "Creating DLQ..."
$AWS_CMD sqs create-queue --queue-name events-dlq

DLQ_ARN=$($AWS_CMD sqs get-queue-attributes \
  --queue-url "$ENDPOINT/000000000000/events-dlq" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

echo "DLQ ARN: $DLQ_ARN"

echo "Creating main events queue with redrive policy..."
$AWS_CMD sqs create-queue \
  --queue-name events-queue \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

echo "Creating SNS topic..."
TOPIC_ARN=$($AWS_CMD sns create-topic --name events-topic --query 'TopicArn' --output text)
echo "Topic ARN: $TOPIC_ARN"

echo "Subscribing events-queue to events-topic..."
QUEUE_ARN=$($AWS_CMD sqs get-queue-attributes \
  --queue-url "$ENDPOINT/000000000000/events-queue" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

$AWS_CMD sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol sqs \
  --notification-endpoint "$QUEUE_ARN"

echo "Creating DynamoDB events table..."
$AWS_CMD dynamodb create-table \
  --table-name events \
  --key-schema \
    AttributeName=tenant_id,KeyType=HASH \
    AttributeName=sort_key,KeyType=RANGE \
  --attribute-definitions \
    AttributeName=tenant_id,AttributeType=S \
    AttributeName=sort_key,AttributeType=S \
  --billing-mode PAY_PER_REQUEST

echo "Infrastructure setup complete."
