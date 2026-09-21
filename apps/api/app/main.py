from fastapi import FastAPI

from app.api.race import router as race_router
from app.api.stream import router as stream_router

app = FastAPI(title="VersusLab API")

app.include_router(stream_router)
app.include_router(race_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}