from uuid import UUID, uuid4

from app.generations.models import Generation


class GenerationManager:
    def __init__(self):
        self._generations: dict[UUID, Generation] = {}

    def create_generation(self) -> Generation:
        generation_id = uuid4()

        generation = Generation(
            generation_id=generation_id
        )

        self._generations[generation_id] = generation

        return generation

    def get_generation(self, generation_id: UUID) -> Generation | None:
        return self._generations.get(generation_id)