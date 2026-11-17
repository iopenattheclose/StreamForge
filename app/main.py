from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.generations.manager import GenerationManager
from app.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.generation_manager = GenerationManager(
        queue_max_size=settings.queue_max_size,
        max_active_generations=settings.max_active_generations,
    )

    yield

    # Shutdown cleanup will be added later.


app = FastAPI(
    title="StreamForge",
    description="High-concurrency asynchronous SSE streaming gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )