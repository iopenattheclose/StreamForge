from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID


class GenerationStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"

@dataclass
class Generation:
    generation_id: UUID
    status: GenerationStatus = GenerationStatus.CREATED

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    started_at: datetime | None = None
    completed_at: datetime | None = None

    token_count: int = 0
    error: str | None = None