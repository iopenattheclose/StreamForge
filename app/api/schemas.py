from pydantic import BaseModel, Field
from uuid import UUID


class GenerationCreateData(BaseModel):
    generation_id: UUID
    status: str


class GenerationCreateResponse(BaseModel):
    data: GenerationCreateData

class GenerationCreateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)
    max_tokens: int = Field(gt=0, le=10000)