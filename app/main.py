from fastapi import FastAPI
from app.config import settings
import uvicorn

app = FastAPI(
    title="StreamForge",
    description="High-concurrency asynchronous SSE streaming gateway",
    version="0.1.0",
)


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