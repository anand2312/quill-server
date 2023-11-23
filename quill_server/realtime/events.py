from enum import StrEnum, auto
from functools import partial
from typing import Any, Generic, TypeVar
from collections.abc import Awaitable
import typing

from loguru import logger
from pydantic import BaseModel
from redis.asyncio import Redis

from quill_server.db.models import User
from quill_server.realtime.room import GameMember, Room, ChatMessage, _db_user_to_game_member
from quill_server.schema import MessageResponse


DataT = TypeVar("DataT", bound=BaseModel)


# the excalidraw element event contains many fields
# https://github.com/excalidraw/excalidraw/blob/master/src/element/types.ts#L27-L141
ExcalidrawElement = dict[str, Any]


class Drawing(BaseModel):
    user: GameMember
    elements: list[ExcalidrawElement]


class EventType(StrEnum):
    START = auto()  # sent by the user to the server to trigger a game start
    CONNECT = auto()  # sent to the newly joined user
    MEMBER_JOIN = auto()  # sent to all connected users when a new user joins
    MEMBER_LEAVE = auto()  # sent to all connected users when a user disconnects from the room
    OWNER_CHANGE = auto()  # sent when the room owner changes
    GAME_STATE_CHANGE = auto()  # sent when the game starts or ends
    MESSAGE = auto()  # sent when any user sends a message in the chat
    CORRECT_GUESS = auto()  # sent when any user makes a correct guess
    DRAWING = auto()  # sent when a user is drawing on the board
    TURN_START = auto()  # sent when a new turn starts
    TURN_END = auto()  # sent when a turn ends
    ERROR = auto()  # sent to a user if it tries some illegal action


class Event(BaseModel, Generic[DataT]):
    """An event to be broadcasted."""

    event_type: EventType
    data: DataT


ConnectEvent = partial(Event[Room], event_type=EventType.CONNECT)
MemberJoinEvent = partial(Event[GameMember], event_type=EventType.MEMBER_JOIN)
MemberLeaveEvent = partial(Event[GameMember], event_type=EventType.MEMBER_LEAVE)
ChatMessageEvent = partial(Event[ChatMessage], event_type=EventType.MESSAGE)
CorrectGuessEvent = partial(Event[ChatMessage], event_type=EventType.CORRECT_GUESS)
GameStateChangeEvent = partial(Event[Room], event_type=EventType.GAME_STATE_CHANGE)
DrawingEvent = partial(Event[Drawing], event_type=EventType.DRAWING)


async def process_message(msg: dict[str, Any], room: Room, user: User, conn: Redis) -> Event:
    event_type = msg.get("event_type")
    event_data = msg.get("data")
    if not event_type:
        raise ValueError("Malformed message - no event_type found")
    if not event_data:
        raise ValueError("Malformed message - no event data found")

    match EventType(event_type):
        case EventType.START:
            if str(user.id) == room.owner.user_id:
                await room.start()
                return GameStateChangeEvent(data=room)
            else:
                # user is not the room owner
                data = MessageResponse(message="You do not own this room")
                return Event[MessageResponse](event_type=EventType.ERROR, data=data)
        case EventType.MESSAGE:
            # check if this user has already correctly guessed the answer
            # or if this message is the correct guess
            has_guessed = await typing.cast(
                Awaitable[int], conn.sismember(f"room:{room.room_id}:guessed", str(user.id))
            )
            has_guessed = bool(has_guessed)
            answer_res = await conn.get(f"room:{room.room_id}:answer")
            if not answer_res:
                logger.warning(f"Correct answer not found for room:{room.room_id}")
                chat_message = ChatMessage(
                    username=user.username, message=event_data["message"], has_guessed=has_guessed
                )
                return ChatMessageEvent(data=chat_message)
            answer = answer_res.decode()
            if event_data["message"].lower() == answer.lower() and not has_guessed:
                # add this user to the set of users who have guessed correctly
                await typing.cast(
                    Awaitable[int], conn.sadd(f"room:{room.room_id}:guessed", str(user.id))
                )
                # replace the message content with a success message
                chat_message = ChatMessage(
                    username=user.username, message="Just guessed the answer!", has_guessed=True
                )
                return CorrectGuessEvent(data=chat_message)
            elif event_data["message"].lower() == answer.lower():
                # a user who has already guessed the answer is trying to leak the answer
                chat_message = ChatMessage(username=user.username, message="****", has_guessed=True)
                return ChatMessageEvent(data=chat_message)
            else:
                chat_message = ChatMessage(
                    username=user.username, message=event_data["message"], has_guessed=has_guessed
                )
                return ChatMessageEvent(data=chat_message)
        case EventType.DRAWING:
            drawing = Drawing(
                user=_db_user_to_game_member(user), elements=event_data.get("elements")
            )
            return DrawingEvent(data=drawing)
        case _:
            return Event(event_type=event_type, data=event_data)
