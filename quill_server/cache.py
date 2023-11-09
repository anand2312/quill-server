from loguru import logger
import redis.asyncio as redis

client = redis.Redis(decode_responses=True)


async def disconnect() -> None:
    """Close the connection to Redis"""
    logger.info("Closing connection to redis")
    await client.aclose()
