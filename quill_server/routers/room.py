import asyncio
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from quill_server import cache
from quill_server.auth import get_current_session_ws, get_current_user, get_current_user_ws
from quill_server.db.connect import get_db
from quill_server.db.models import User
from quill_server.realtime.events import EventType, process_message
from quill_server.realtime.game_loop import game_loop
from quill_server.realtime.pubsub import Broadcaster
from quill_server.realtime.room import get_current_room, Room


router = APIRouter(prefix="/room", tags=["room"])

_bg_tasks = set()


@router.post("/")
async def create_room(user: Annotated[User, Depends(get_current_user)]) -> Room:
    room = Room.new(user)
    await room.to_redis()
    task = asyncio.create_task(game_loop(cache.client, room.room_id))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return room


@router.websocket("/{room_id}")
async def room_socket(
    ws: WebSocket,
    db: Annotated[AsyncSession, Depends(get_db)],
    room: Annotated[Room | None, Depends(get_current_room)],
) -> None:
    if not room:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Room not found")
    await ws.accept()

    # the first message the user sends will be the authorization
    # if it is not valid - reject the connection
    auth_msg: dict[str, str] = await ws.receive_json()
    token_text = auth_msg.get("Authorization")
    if not token_text:
        raise WebSocketException(status.WS_1008_POLICY_VIOLATION, "Authorization not sent")
    try:
        session = await get_current_session_ws(token_text)
    except TypeError:
        # a typeerror is raised if the token sent was not a valid UUID
        raise WebSocketException(
            status.WS_1008_POLICY_VIOLATION, "Authorization not sent"
        ) from None
    user = await get_current_user_ws(session, db)

    try:
        await room.join(user)  # add the user to list of connected users
    except ValueError as e:
        raise WebSocketException(status.WS_1008_POLICY_VIOLATION, e.args[0]) from None

    broadcaster = Broadcaster(ws, cache.client, user, room)
    task = asyncio.create_task(broadcaster.listen())
    await broadcaster.join()

    try:
        while True:
            data = await ws.receive_json()
            event = await process_message(data, room, user, cache.client, db)
            # error events need not be emitted to everyone
            if event.event_type == EventType.ERROR:
                await broadcaster.send_personal(event)
            else:
                await broadcaster.emit(event)
    except WebSocketDisconnect:
        await room.leave(user)  # remove the user from the list of connected users
        await broadcaster.leave()
        await task
