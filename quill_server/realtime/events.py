from enum import StrEnum, auto
from functools import partial
from typing import Generic, TypeVar

from pydantic import BaseModel

from quill_server.realtime.room import GameMember, Room


DataT = TypeVar("DataT", bound=BaseModel)


class EventType(StrEnum):
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


class Event(BaseModel, Generic[DataT]):
    """An event to be broadcasted."""

    event_type: EventType
    data: DataT


ConnectEvent = partial(Event[Room], event_type=EventType.CONNECT)
MemberJoinEvent = partial(Event[GameMember], event_type=EventType.MEMBER_JOIN)
MemberLeaveEvent = partial(Event[GameMember], event_type=EventType.MEMBER_LEAVE)
