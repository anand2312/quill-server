from fastapi import FastAPI

from .schema import MessageResponse

app = FastAPI(title="Quill")


@app.get("/ping")
async def ping() -> MessageResponse:
    return MessageResponse(message="Pong!")
