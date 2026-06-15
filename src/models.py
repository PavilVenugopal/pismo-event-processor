# Event model defines what every incoming message must look like.
# ProcessedEvent extends it with tracking fields we write to DynamoDB.
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class Event(BaseModel):
    event_id: str
    event_type: str
    tenant_id: str
    timestamp: str
    schema_version: str = "1.0"
    payload: dict[str, Any]


class ProcessedEvent(BaseModel):
    event_id: str
    event_type: str
    tenant_id: str
    timestamp: str
    schema_version: str
    payload: dict[str, Any]
    processed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "valid"
