from fastapi import APIRouter
from fastapi import Request, status

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

    generation = manager.create_generation()

    return GenerationCreateResponse(
        data=GenerationCreateData(
            generation_id=generation.generation_id,
            status=generation.status.value,
        )
    )