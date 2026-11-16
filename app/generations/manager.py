from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.generations.models import (
    Generation,
    GenerationRuntime,
    GenerationStatus,
)
import asyncio


class GenerationNotFoundError(Exception):
    pass


class InvalidGenerationStateError(Exception):
    pass


class GenerationManager:
    def __init__(
        self,
        queue_max_size: int,
        max_active_generations: int,
    ):
        self._generations: dict[UUID, Generation] = {}
        self._runtimes: dict[UUID, GenerationRuntime] = {}

        self._queue_max_size = queue_max_size
        self._max_active_generations = max_active_generations


    def _active_generation_count(self) -> int:
        return sum(
            1
            for generation in self._generations.values()
            if generation.status in (
                GenerationStatus.CREATED,
                GenerationStatus.RUNNING,
            )
    )

    def remove_runtime(self, generation_id: UUID) -> None:
        self._runtimes.pop(generation_id, None)

    def create_generation(self) -> Generation:

        if self._active_generation_count() >= self._max_active_generations:
            raise GenerationCapacityError(
                "Maximum active generation capacity reached"
            )
        
        generation_id = uuid4()

        generation = Generation(
            generation_id=generation_id
        )

        runtime = GenerationRuntime(
            token_queue=asyncio.Queue(maxsize=self._queue_max_size)
        )

        self._generations[generation_id] = generation
        self._runtimes[generation_id] = runtime

        return generation

    def get_generation(self, generation_id: UUID) -> Generation | None:
        return self._generations.get(generation_id)

    def start_generation(self, generation_id: UUID) -> Generation:

        generation = self.get_generation(generation_id)

        if generation is None:
            raise GenerationNotFoundError(
                f"Generation {generation_id} not found"
            )

        if generation.status != GenerationStatus.CREATED:
            raise InvalidGenerationStateError(
                f"Cannot start generation in {generation.status.value} state"
        )

        generation.status = GenerationStatus.RUNNING
        generation.started_at = datetime.now(timezone.utc)

        return generation


    def complete_generation(self, generation_id: UUID) -> Generation:

        generation = self.get_generation(generation_id)

        if generation is None:
            raise GenerationNotFoundError(
                f"Generation {generation_id} not found"
            )

        if generation.status != GenerationStatus.RUNNING:
            raise InvalidGenerationStateError(
                f"Cannot complete generation in {generation.status.value} state"
            )

        generation.status = GenerationStatus.COMPLETED
        generation.completed_at = datetime.now(timezone.utc)

        return generation


    def fail_generation(self, generation_id: UUID, error: str) -> Generation:

        generation = self.get_generation(generation_id)

        if generation is None:
            raise GenerationNotFoundError(
                f"Generation {generation_id} not found"
            )

        if generation.status != GenerationStatus.RUNNING:
            raise InvalidGenerationStateError(
                f"Cannot fail generation in {generation.status.value} state"
            )

        generation.status = GenerationStatus.FAILED
        generation.completed_at = datetime.now(timezone.utc)
        generation.error = error

        return generation

    def cancel_generation(self, generation_id: UUID) -> Generation:
        generation = self.get_generation(generation_id)

        if generation is None:
            raise GenerationNotFoundError(
                f"Generation {generation_id} not found"
            )

        if generation.status == GenerationStatus.CANCELLED:
            return generation

        if generation.status not in (
            GenerationStatus.CREATED,
            GenerationStatus.RUNNING,
        ):
            raise InvalidGenerationStateError(
                f"Cannot cancel generation in {generation.status.value} state"
            )

        generation.status = GenerationStatus.CANCELLED
        generation.completed_at = datetime.now(timezone.utc)

        return generation


    def expire_generation(self, generation_id: UUID) -> Generation:
        generation = self.get_generation(generation_id)

        if generation is None:
            raise GenerationNotFoundError(
                f"Generation {generation_id} not found"
            )

        if generation.status != GenerationStatus.CREATED:
            raise InvalidGenerationStateError(
                f"Cannot expire generation in {generation.status.value} state"
            )

        generation.status = GenerationStatus.EXPIRED
        generation.completed_at = datetime.now(timezone.utc)

        return generation

    def get_runtime(self, generation_id: UUID) -> GenerationRuntime | None:
        return self._runtimes.get(generation_id)


class GenerationCapacityError(Exception):
    pass