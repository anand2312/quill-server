from fastapi import FastAPI

from quill_server.schema import MessageResponse
from quill_server.routers import user

app = FastAPI(title="Quill")

app.include_router(user.router)


@app.get("/ping")
async def ping() -> MessageResponse:
    return MessageResponse(message="Pong!")
