from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from quill_server import cache
from quill_server.schema import MessageResponse
from quill_server.routers import user


@asynccontextmanager
async def lifetime(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await cache.disconnect()


app = FastAPI(title="Quill", lifespan=lifetime)

origins = ["http://localhost:3000", "https://quill-teal-omega.vercel.app"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user.router)


@app.get("/ping")
async def ping() -> MessageResponse:
    return MessageResponse(message="Pong!")
