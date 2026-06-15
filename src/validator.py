# Loads JSON schemas from the schemas/ directory and validates event payloads against them.
# To add a new event type, drop a .json file in schemas/ — nothing else needs to change.
from __future__ import annotations

import json
import logging
from pathlib import Path

import jsonschema

from src.models import Event

logger = logging.getLogger(__name__)


class SchemaValidator:
    def __init__(self, schemas_dir: str):
        self.schemas_dir = Path(schemas_dir)
        self._cache: dict[str, dict] = {}
        self._load_schemas()

    def _load_schemas(self):
        if not self.schemas_dir.exists():
            logger.warning(f"Schemas directory not found: {self.schemas_dir}")
            return
        for schema_file in self.schemas_dir.glob("*.json"):
            event_type = schema_file.stem
            with open(schema_file) as f:
                self._cache[event_type] = json.load(f)
            logger.debug(f"Loaded schema for: {event_type}")

    def validate(self, event: Event) -> tuple:
        schema = self._cache.get(event.event_type)
        if schema is None:
            return False, f"No schema found for event type: {event.event_type}"
        try:
            jsonschema.validate(instance=event.payload, schema=schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, e.message
