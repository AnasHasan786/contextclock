from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.memories import router as memories_router

app = FastAPI(
    title="ContextClock",
    description="Staleness scoring for AI agent memories.",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(memories_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}