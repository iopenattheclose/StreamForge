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
    GenerationStatusResponse,
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
        max_tokens=generation.max_tokens,
    )

    async def stream():
        try:
            async for chunk in consume_tokens(runtime.token_queue):
                yield chunk

            await runtime.producer_task
            manager.complete_generation(generation_id)

        except asyncio.CancelledError:
            manager.cancel_generation(generation_id)
            raise

        except Exception as exc:
            manager.fail_generation(
                generation_id,
                error=str(exc),
            )
            raise

        finally:
            if runtime.producer_task:
                if not runtime.producer_task.done():
                    runtime.producer_task.cancel()

                try:
                    await runtime.producer_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            manager.remove_runtime(generation_id)


    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
    )

@router.get(
    "/generations/{generation_id}",
    response_model=GenerationStatusResponse,
)
async def get_generation_status(
    generation_id: UUID,
    request: Request,
):
    manager = request.app.state.generation_manager

    generation = manager.get_generation(generation_id)

    if generation is None:
        raise HTTPException(
            status_code=404,
            detail="Generation not found",
        )

    return GenerationStatusResponse(
        generation_id=generation.generation_id,
        status=generation.status.value,
        token_count=generation.token_count,
        created_at=generation.created_at,
        started_at=generation.started_at,
        completed_at=generation.completed_at,
        error=generation.error,
    )