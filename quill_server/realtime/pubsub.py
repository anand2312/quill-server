import asyncio
import json
import typing
from dataclasses import dataclass

from fastapi import WebSocket
from loguru import logger
from redis.exceptions import ConnectionError
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from quill_server.db.models import User
from quill_server.realtime.events import (
    ConnectEvent,
    Event,
    EventType,
    MemberJoinEvent,
    MemberLeaveEvent,
)
from quill_server.realtime.room import Room, _db_user_to_game_member


# set of scheduled Tasks
# this is done as the event loop does not keep any strong refs
# to scheduled tasks, and they may get garbage collected before
# completion. so we add them to this set (thereby creating strong refs)
# and not allowing them to be garbage collected.
# read: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_bg_tasks = set()


@dataclass
class Broadcaster:
    ws: WebSocket
    conn: Redis
    user: User
    room: Room

    async def _loop(self, pubsub: PubSub) -> None:
        connect_tries = 0
        await pubsub.subscribe(f"room:{self.room.room_id}")
        while True:
            try:
                message = await typing.cast(
                    typing.Awaitable[dict[str, typing.Any] | None],
                    pubsub.get_message(ignore_subscribe_messages=True),
                )
            except ConnectionError:
                connect_tries += 1
                if connect_tries == 50:
                    logger.warning(
                        "Pubsub could not connect to Redis after 50 retries. Is redis running?"
                    )
                    return
                else:
                    continue
            if message is not None:
                event = json.loads(message["data"])
                event_type = EventType(event["event_type"])
                # the listener should stop in two cases:
                # either the game has ended (event["data"]["status"] == "ended")
                if event_type == EventType.GAME_STATE_CHANGE and event["data"]["status"] == "ended":
                    # in this case, emit the event and then end the loop
                    await self.ws.send_json(event)
                    return
                # OR the current user has left the room (event_type = MEMBER_LEAVE and
                # event["data"]["user_id"] == self.user.id).
                # in this case we do not have to emit the event to this user
                elif event_type == EventType.MEMBER_LEAVE and event["data"]["user_id"] == str(
                    self.user.id
                ):
                    await self.ws.close()
                    return
                await self.ws.send_json(event)

    async def listen(self) -> None:
        """Subscribe to the room's channel on Redis, and send the received messages over the websocket."""
        async with self.conn.pubsub() as pubsub:
            task = asyncio.create_task(
                self._loop(pubsub), name=f"room:{self.room.room_id}:user:{self.user.id}"
            )
            _bg_tasks.add(task)
            task.add_done_callback(_bg_tasks.discard)

    async def emit(self, event: Event) -> None:
        """Emit an event to the pubsub channel, to be picked up by all subscribers."""
        await self.conn.publish(f"room:{self.room.room_id}", event.model_dump_json())

    async def send_personal(self, event: Event) -> None:
        """Send an event to only the websocket client associated with this broadcaster."""
        await self.ws.send_json(event.model_dump())

    async def join(self) -> None:
        """Sends a CONNECT event to the newly joined client, and a MEMBER_JOIN event to everyone else."""
        await self.send_personal(ConnectEvent(data=self.room))
        await self.emit(MemberJoinEvent(data=_db_user_to_game_member(self.user)))

    async def leave(self) -> None:
        """Sends a MEMBER_LEAVE event to everyone."""
        await self.emit(MemberLeaveEvent(data=_db_user_to_game_member(self.user)))
