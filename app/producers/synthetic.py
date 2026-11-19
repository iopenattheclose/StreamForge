import asyncio
from app.generations.models import QueueSignal

class SyntheticProducer:
    def __init__(self, token_delay: float):
        self._token_delay = token_delay

    async def generate(
        self,
        prompt: str,
        max_tokens: int,
        token_queue: asyncio.Queue[str | QueueSignal],
        on_token,
    ):
        try:
            tokens = prompt.split()[:max_tokens]

            for token in tokens:
                await token_queue.put(token)
                on_token()
                await asyncio.sleep(self._token_delay)

            await token_queue.put(QueueSignal.FINISHED)

        except asyncio.CancelledError:
            raise

        except Exception:
            await token_queue.put(QueueSignal.ERROR)
            raise