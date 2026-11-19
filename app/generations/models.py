from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID
import asyncio

class GenerationStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"

class QueueSignal(str, Enum):
    FINISHED = "finished"
    ERROR = "error"
    
@dataclass
class Generation:
    generation_id: UUID
    prompt: str
    max_tokens: int
    status: GenerationStatus = GenerationStatus.CREATED


    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    started_at: datetime | None = None
    completed_at: datetime | None = None

    token_count: int = 0
    error: str | None = None

@dataclass
class GenerationRuntime:
    token_queue: asyncio.Queue[str | QueueSignal]
    producer_task: asyncio.Task | None = None
