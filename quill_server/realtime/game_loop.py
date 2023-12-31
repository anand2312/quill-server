import asyncio
import contextlib
import json
import random
import typing
from functools import cache

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from quill_server.realtime.events import Event, EventType, GameStateChangeEvent
from quill_server.realtime.room import GameMember, GameStatus, Room, TurnEndData, TurnStartData


@cache
def words() -> list[str]:
    with open("public/source.txt") as f:
        return f.readlines()


# TODO: refactor? this code is so jank
async def game_loop(cache: Redis, room_id: str) -> None:
    logger.info(f"Game Loop[room={room_id}]: loop registered")
    connect_tries = 0
    async with cache.pubsub() as pubsub:
        await pubsub.subscribe(f"room:{room_id}")
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

                if event_type == EventType.GAME_STATE_CHANGE:
                    status = event["data"]["status"]
                    if status == "ongoing":
                        logger.info(
                            f"Game Loop[room={room_id}]: Received GAME_STATE_CHANGE(start) event"
                        )
                        await rounds_loop(cache, room_id)
                        # after the rounds loop has finished, send a GAME_STATE_CHANGE(ended) event
                        # first, set the room's status as ended in redis
                        await cache.set(f"room:{room_id}:status", str(GameStatus.ENDED))
                        # next, fetch the entire room's data from redis
                        room = await Room.from_redis(room_id)
                        if not room:
                            logger.error(
                                f"Game Loop[room={room_id}]: room couldn't be retrieved from redis. "
                                f"This should NEVER happen."
                            )
                            return
                        event = GameStateChangeEvent(data=room)
                        logger.info(f"Game Loop[room={room_id}]: Sent GAME_STATE_CHANGE(end) event")
                        await cache.publish(f"room:{room_id}", event.model_dump_json())
                        return


async def _get_users(cache: Redis, room: str) -> list[GameMember]:
    users_res = await typing.cast(
        typing.Awaitable[list[bytes]], cache.lrange(f"room:{room}:users", 0, -1)
    )
    return [GameMember.model_validate_json(i) for i in users_res]


async def poll_until_everyone_guesses(cache: Redis, room: str) -> None:
    """
    Keep polling redis until everyone in this room has guessed the answer.
    This must be called with a timeout set.
    """
    while True:
        guesses = await typing.cast(typing.Awaitable[int], cache.scard(f"room:{room}:guessed"))
        n_members = await typing.cast(typing.Awaitable[int], cache.llen(f"room:{room}:users"))
        if guesses == n_members:
            logger.info(f"Game Loop[room={room}]: everyone has guessed")
            return


async def rounds_loop(
    cache: Redis, room_id: str, n_rounds: int = 1, sec_per_round: int = 60
) -> None:
    # get the number of members initially
    n_members = await typing.cast(typing.Awaitable[int], cache.llen(f"room:{room_id}:users"))
    # get at least n_members * n_rounds random words
    word_pool = [word.strip() for word in random.choices(words(), k=n_members * n_rounds)]
    # room:id:current_draw_user stores the index of the user who has to draw next
    for i in range(n_rounds):
        logger.info(f"Game Loop[room={room_id}]: Round {i + 1} starting")
        users = await _get_users(cache, room_id)
        for idx, user in enumerate(users):
            # step 0: ensure this user is still connected
            is_still_connected = await typing.cast(
                typing.Awaitable[int | str],
                cache.lpos(f"room:{room_id}:users", user.model_dump_json()),
            )
            if not isinstance(is_still_connected, int):
                # LPOS should return the index at which the element is found
                # If the element wasn't found, LPOS returned nil, which is not an int
                logger.info(
                    f"Game Loop[room={room_id}]: User {user.username} is no longer connected; skipping"
                )
                continue
            # step 1: set the answer for this turn
            answer = word_pool.pop()
            logger.info(f"Game Loop[room={room_id}]: set room:{room_id}:answer={answer}")
            await cache.set(f"room:{room_id}:answer", answer)
            # step 2: initialize the set of users who have guessed the answer
            # add the user who is drawing to the set, so that we won't be waiting
            # for them to correctly guess their own drawing
            await typing.cast(
                typing.Awaitable[int], cache.sadd(f"room:{room_id}:guessed", user.user_id)
            )
            start_data = TurnStartData(user=GameMember.model_validate(user), answer=answer)
            logger.info(
                f"Game Loop[room={room_id}]: User {user.username}'s turn to draw; answer is {start_data.answer}"
            )
            # step 3: send the TURN_START event
            start_event = Event[TurnStartData](event_type=EventType.TURN_START, data=start_data)
            await cache.publish(f"room:{room_id}", start_event.model_dump_json())
            # step 4: wait for 60 seconds, or until every user has guessed the answer (whichever comes first)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    poll_until_everyone_guesses(cache, room_id), timeout=sec_per_round
                )
            # step 5: clear the room:{id}:guessed set
            await cache.delete(f"room:{room_id}:guessed")
            # step 6: publish TURN_END event
            end_data = TurnEndData(turn=idx)
            end_event = Event[TurnEndData](event_type=EventType.TURN_END, data=end_data)
            await cache.publish(f"room:{room_id}", end_event.model_dump_json())
            # step 7: sleep for 2 seconds to add some cooldown between rounds
            await asyncio.sleep(2)
