import typing
from enum import StrEnum, auto
from json import loads
from uuid import uuid4, UUID

from fastapi import Path
from loguru import logger
from pydantic import BaseModel

from quill_server import cache
from quill_server.db.models import User


class GameStatus(StrEnum):
    LOBBY = auto()
    ONGOING = auto()
    ENDED = auto()


class GameMember(BaseModel):
    """Represents a user currently playing in a Quill room."""

    user_id: str
    username: str


class TurnStartData(BaseModel):
    """Represents the data sent whenever a new turn starts."""

    user: GameMember
    answer: str


class TurnEndData(BaseModel):
    """Represents the data sent whenever a turn ends."""

    # for now, we don't really need to send anything at turn end
    turn: int


class ChatMessage(BaseModel):
    """Represents a message sent by a Quill player."""

    username: str
    message: str
    has_guessed: bool


def _db_user_to_game_member(user: User) -> GameMember:
    return GameMember(user_id=str(user.id), username=user.username)


class Room(BaseModel):
    """Represents a Quill game room."""

    room_id: str
    owner: GameMember
    users: list[GameMember]
    status: GameStatus

    @classmethod
    def new(cls: type["Room"], owner: User) -> "Room":
        return cls(
            room_id=str(uuid4()),
            owner=_db_user_to_game_member(owner),
            users=[],
            status=GameStatus.LOBBY,
        )

    async def start(self) -> None:
        """Start the game in this room."""
        self.status = GameStatus.ONGOING
        logger.info(f"Setting room:{self.room_id}:status = ONGOING")
        await cache.client.set(f"room:{self.room_id}:status", str(self.status))

    async def end(self) -> None:
        """End the game in this room."""
        self.status = GameStatus.ENDED
        logger.info(f"Setting room:{self.room_id}:status = ENDED")
        await cache.client.set(f"room:{self.room_id}:status", str(self.status))

    async def has_member(self, user: User) -> bool:
        """Check if the given user is connected to this room."""
        user_string = _db_user_to_game_member(user).model_dump_json()
        # LPOS returns an integer index if the element was found in the list, and otherwise returns nil
        # if LPOS returned an int, the member exists in the room
        pos = await typing.cast(
            typing.Awaitable[int | str],
            cache.client.lpos(f"room:{self.room_id}:users", user_string),
        )
        return isinstance(pos, int)

    async def join(self, user: User) -> None:
        """Add a user to this room."""
        # reject connection if the user is already in the room...
        if any([u.user_id == str(user.id) for u in self.users]):
            raise ValueError("User is already in this room")
        # or if the game isn't in the lobby state anymore...
        elif self.status != GameStatus.LOBBY:
            raise ValueError("Room is no longer accepting members")
        # or if the room already has 8 members
        elif len(self.users) == 8:
            raise ValueError("Maximum room capacity reached")
        data = _db_user_to_game_member(user)
        self.users.append(data)
        logger.info(f"Adding {data.username} to room:{self.room_id}")
        await typing.cast(
            typing.Awaitable[int],
            cache.client.rpush(f"room:{self.room_id}:users", data.model_dump_json()),
        )

    async def leave(self, user: User) -> None:
        """Remove a user from this room."""
        data = _db_user_to_game_member(user)
        self.users.remove(data)
        logger.info(f"Removing {data.username} from room:{self.room_id}")
        res = await typing.cast(
            typing.Awaitable[int],
            cache.client.lrem(f"room:{self.room_id}:users", 1, data.model_dump_json()),
        )
        if res != 1:
            logger.warning(
                f"Attempted removing {data.username} from room:{self.room_id} "
                f"but Redis gave a response != 1 ({res=})"
            )

    async def to_redis(self) -> None:
        """Writes the room to Redis."""
        # all the dictionaries are being dumped to redis as JSON strings
        # room:id:users will be a list of JSON strings
        key = f"room:{self.room_id}"
        owner = self.owner.model_dump_json()
        users = [i.model_dump_json() for i in self.users]
        status = str(self.status)
        logger.info(f"Writing {key} to Redis")
        async with cache.client.pipeline(transaction=True) as pipe:
            pipe.set(f"{key}:owner", owner)
            pipe.set(f"{key}:status", str(status))
            if len(users) > 0:
                pipe.rpush(f"{key}:users", *users)
            await pipe.execute()
        logger.info(f"Saved {key} to Redis")

    @classmethod
    async def from_redis(cls: type["Room"], room_id: str) -> typing.Optional["Room"]:
        key = f"room:{room_id}"
        logger.info(f"Fetching {key} from Redis")
        status = await cache.client.get(f"{key}:status")
        if not status:
            logger.warning(f"{key} does not exist in cache")
            return
        owner_res = await cache.client.get(f"{key}:owner")
        owner = loads(owner_res)
        # redis-py has incorrect return types set, so we need to cast here
        # https://github.com/redis/redis-py/issues/2933
        users_res = await typing.cast(
            typing.Awaitable[list[bytes]], cache.client.lrange(f"{key}:users", 0, -1)
        )
        users = [loads(i) for i in users_res]
        return cls(room_id=room_id, owner=owner, users=users, status=status.decode())


# ruff complains about the Path() call, but this is FastAPI convention
async def get_current_room(room_id: UUID = Path(...)) -> Room | None:  # noqa: B008
    return await Room.from_redis(str(room_id))
