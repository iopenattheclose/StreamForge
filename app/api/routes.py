from fastapi import APIRouter
from fastapi import Request, status
from uuid import UUID
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from app.streaming.sse import consume_tokens
import asyncio
from app.api.schemas import (
    GenerationCreateData,
    GenerationCreateRequest,
    GenerationCreateResponse,
)

router = APIRouter(prefix="/api/v1")


@router.post(
    "/generations",
    response_model=GenerationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_generation(
    payload: GenerationCreateRequest,
    request: Request,
):
    manager = request.app.state.generation_manager

    generation = manager.create_generation(
        prompt=payload.prompt,
        max_tokens=payload.max_tokens,
    )

    return GenerationCreateResponse(
        data=GenerationCreateData(
            generation_id=generation.generation_id,
            status=generation.status.value,
        )
    )

@router.get("/generations/{generation_id}/stream")
async def stream_generation(
    generation_id: UUID,
    request: Request,
):
    manager = request.app.state.generation_manager
    producer = request.app.state.producer

    generation = manager.get_generation(generation_id)

    if generation is None:
        raise HTTPException(
            status_code=404,
            detail="Generation not found",
        )

    if generation.status.value != "created":
        raise HTTPException(
            status_code=409,
            detail="Generation cannot be streamed",
        )

    manager.start_generation(generation_id)

    runtime = manager.get_runtime(generation_id)

    manager.start_producer(
        generation_id=generation_id,
        producer=producer,
        prompt=generation.prompt,
    )

    async def stream():
        try:
            async for chunk in consume_tokens(runtime.token_queue):
                yield chunk

            manager.complete_generation(generation_id)

        except asyncio.CancelledError:
            manager.cancel_generation(generation_id)
            raise

        finally:
            if runtime.producer_task and not runtime.producer_task.done():
                runtime.producer_task.cancel()

                try:
                    await runtime.producer_task
                except asyncio.CancelledError:
                    pass

            manager.remove_runtime(generation_id)


    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
    )