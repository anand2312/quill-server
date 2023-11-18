import asyncio
import json
from dataclasses import dataclass

from fastapi import WebSocket
from loguru import logger
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


@dataclass
class Broadcaster:
    ws: WebSocket
    conn: Redis
    user: User
    room: Room

    async def _loop(self, pubsub: PubSub) -> None:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if not message:
                logger.warning(
                    f"PubSub channel {self.room.room_id} gave a None message - breaking loop."
                )
                return
            event = json.loads(message["data"])
            event_type = EventType(event["event_type"])
            # the listener should stop in two cases:
            # either the game has ended (event["data"]["status"] == "ended")
            # OR the current user has left the room (event_type = MEMBER_LEAVE and
            # event["data"]["user_id"] == self.user.id)
            if (
                event_type == EventType.GAME_STATE_CHANGE and event["data"]["status"] == "ended"
            ) or (
                event_type == EventType.MEMBER_LEAVE
                and event["data"]["user_id"] == str(self.user.id)
            ):
                return
            await self.ws.send_json(event)

    async def listen(self) -> None:
        """Subscribe to the room's channel on Redis, and send the received messages over the websocket."""
        async with self.conn.pubsub() as pubsub:
            await pubsub.subscribe(f"room:{self.room.room_id}")
            _ = asyncio.create_task(
                self._loop(pubsub), name=f"room:{self.room.room_id}:user:{self.user.id}"
            )

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
