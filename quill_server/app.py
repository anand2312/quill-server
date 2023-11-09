from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from quill_server import cache
from quill_server.schema import MessageResponse
from quill_server.routers import user


@asynccontextmanager
async def lifetime(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await cache.disconnect()


app = FastAPI(title="Quill", lifespan=lifetime)

app.include_router(user.router)


@app.get("/ping")
async def ping() -> MessageResponse:
    return MessageResponse(message="Pong!")
