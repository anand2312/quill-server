from fastapi import FastAPI

from doodle_server.schema import MessageResponse

app = FastAPI(title="Doodle")


@app.get("/ping")
async def ping() -> MessageResponse:
    return MessageResponse(message="Pong!")
