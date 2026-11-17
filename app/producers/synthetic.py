import asyncio
from app.generations.models import QueueSignal

class SyntheticProducer:
    def __init__(self, token_delay: float):
        self._token_delay = token_delay

    async def generate(
    self,
    prompt: str,
    token_queue: asyncio.Queue[str | QueueSignal],
):
        tokens = prompt.split()

        for token in tokens:
            await token_queue.put(token)
            await asyncio.sleep(self._token_delay)

        await token_queue.put(QueueSignal.FINISHED)