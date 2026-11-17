import asyncio

from fastapi.responses import StreamingResponse

from app.generations.models import QueueSignal


def format_sse(token: str) -> str:
    return f"data: {token}\n\n"


async def consume_tokens(token_queue: asyncio.Queue):
    while True:
        item = await token_queue.get()

        try:
            if item == QueueSignal.FINISHED:
                break

            yield format_sse(item)

        finally:
            token_queue.task_done()


def create_sse_response(token_queue: asyncio.Queue) -> StreamingResponse:
    return StreamingResponse(
        consume_tokens(token_queue),
        media_type="text/event-stream",
    )