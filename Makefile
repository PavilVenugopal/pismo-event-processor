.PHONY: install test test-unit test-e2e up down logs clean

install:
	pip install -r requirements-dev.txt

test-unit:
	pytest tests/ --ignore=tests/test_e2e.py --ignore=tests/test_store.py -v

test:
	pytest tests/ --ignore=tests/test_e2e.py -v

test-e2e:
	RUN_INTEGRATION=1 pytest tests/test_e2e.py -v -s

up:
	docker-compose up --build -d

down:
	docker-compose down -v

logs:
	docker-compose logs -f processor

scan-dlq:
	aws --endpoint-url=http://localhost:4566 sqs receive-message \
	  --queue-url http://localhost:4566/000000000000/events-dlq \
	  --region us-east-1 --max-number-of-messages 10

scan-db:
	aws --endpoint-url=http://localhost:4566 dynamodb scan \
	  --table-name events --region us-east-1

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/
