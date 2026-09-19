from fastapi import FastAPI
from app.api.memories import router as memories_router

app = FastAPI(
    title="ContextClock",
    description="Staleness scoring for AI agent memories.",
    version="0.1.0"
)

app.include_router(memories_router);

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}