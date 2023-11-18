from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.responses import JSONResponse

from quill_server import cache
from quill_server.auth import get_current_user
from quill_server.db.models import User
from quill_server.realtime.events import process_message
from quill_server.realtime.pubsub import Broadcaster
from quill_server.realtime.room import get_current_room, Room
from quill_server.schema import MessageResponse


router = APIRouter(prefix="/room")


@router.post("/")
async def create_room(user: Annotated[User, Depends(get_current_user)]) -> Room:
    room = Room.new(user)
    await room.to_redis()
    return room


@router.get("/{room_id}", response_model=Room, responses={404: {"model": MessageResponse}})
async def get_room(
    user: Annotated[User, Depends(get_current_user)],
    room: Annotated[Room | None, Depends(get_current_room)],
) -> JSONResponse | Room:
    if not room:
        return JSONResponse(content={"message": "Room not found"}, status_code=404)
    return room


@router.websocket("/{room_id}")
async def room_socket(
    ws: WebSocket,
    user: Annotated[User, Depends(get_current_user)],
    room: Annotated[Room | None, Depends(get_current_room)],
) -> None:
    if not room:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    await ws.accept()

    broadcaster = Broadcaster(ws, cache.client, user, room)
    await broadcaster.join()

    try:
        while True:
            data = await ws.receive_json()
            event = await process_message(data, room, user, cache.client)
            await broadcaster.emit(event)
    except WebSocketDisconnect:
        await broadcaster.leave()
