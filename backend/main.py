from fastapi import FastAPI

from backend.api.routes import router

app = FastAPI(title="QwenChaNa Medias", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Simple health check endpoint for local development."""

    return {"status": "ok"}
