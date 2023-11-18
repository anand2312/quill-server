from dataclasses import dataclass

from fastapi import WebSocket
from redis.asyncio import Redis

from quill_server.db.models import User
from quill_server.realtime.events import Event


@dataclass
class Broadcaster:
    ws: WebSocket
    conn: Redis
    user: User
    room_id: str

    async def _listen(self) -> None:
        """Subscribe to the room's channel on Redis, and send the received messages over the websocket."""

    async def emit(self, event: Event) -> None:
        """Emit an event to the pubsub channel, to be picked up by all subscribers."""
