import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException, status

from quill_server import cache
from quill_server.auth import get_current_user, get_current_user_ws
from quill_server.db.models import User
from quill_server.realtime.events import process_message
from quill_server.realtime.pubsub import Broadcaster
from quill_server.realtime.room import get_current_room, Room


router = APIRouter(prefix="/room", tags=["room"])


@router.post("/")
async def create_room(user: Annotated[User, Depends(get_current_user)]) -> Room:
    room = Room.new(user)
    await room.to_redis()
    return room


@router.websocket("/{room_id}")
async def room_socket(
    ws: WebSocket,
    user: Annotated[User, Depends(get_current_user_ws)],
    room: Annotated[Room | None, Depends(get_current_room)],
) -> None:
    if not room:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    await ws.accept()
    await room.join(user)  # add the user to list of connected users
    broadcaster = Broadcaster(ws, cache.client, user, room)
    task = asyncio.create_task(broadcaster.listen())
    await broadcaster.join()

    try:
        while True:
            data = await ws.receive_json()
            event = await process_message(data, room, user, cache.client)
            await broadcaster.emit(event)
    except WebSocketDisconnect:
        await broadcaster.leave()
        await task
