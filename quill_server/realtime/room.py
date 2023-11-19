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

    async def join(self, user: User) -> None:
        data = _db_user_to_game_member(user)
        logger.info(f"Adding {data.username} to room:{self.room_id}")
        await typing.cast(
            typing.Awaitable[int],
            cache.client.rpush(f"room:{self.room_id}:users", data.model_dump_json()),
        )

    async def leave(self, user: User) -> None:
        data = _db_user_to_game_member(user)
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
