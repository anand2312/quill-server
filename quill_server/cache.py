from loguru import logger
import redis.asyncio as redis

from quill_server.config import settings


client = redis.from_url(settings.REDIS_URL, decode_responses=False)


async def disconnect() -> None:
    """Close the connection to Redis"""
    logger.info("Closing connection to redis")
    await client.aclose()
