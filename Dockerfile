FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY schemas/ ./schemas/
COPY producer/ ./producer/
COPY scripts/ ./scripts/

ENV PYTHONUNBUFFERED=1
ENV SCHEMAS_DIR=/app/schemas

CMD ["python", "-m", "src.processor"]
