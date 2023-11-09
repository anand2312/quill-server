from abc import ABCMeta, abstractmethod
from datetime import timedelta
from uuid import UUID

from redis.asyncio import Redis
from loguru import logger

from quill_server.errors import AuthError
from quill_server.auth.session import Session


class SessionDoesNotExistError(AuthError):
    """The specified session did not exist in the storage backend."""


class AbstractSessionStorage(metaclass=ABCMeta):
    """An abstract session storage.

    Classes that implement this ABC will be used to store user session details.
    """

    @abstractmethod
    async def get_session(self, _id: str) -> Session | None:
        """Gets a session from the storage. Returns None if the session doesn't exist.

        Args:
            id: The session ID to get
        Returns:
            Session: The session data
            None: The session didn't exist.
        """
        ...

    @abstractmethod
    async def create_session(self, user_id: UUID) -> Session:
        """Creates a session for the provided user and stores it.

        Args:
            user_id: The user to create the session for.
        Returns:
            The session that was created.
        """
        ...

    @abstractmethod
    async def delete_session(self, _id: str) -> None:
        """Deletes a session from the storage.

        Args:
            id: The session ID to delete
        Raises:
            SessionDoesNotExistError: The specified session does not exist.
        """
        ...


class InMemorySessionStorage(AbstractSessionStorage):
    def __init__(self) -> None:
        self._sessions = dict[str, Session]()

    def __contains__(self, _id: str) -> bool:
        return self._sessions.get(_id) is not None

    async def get_session(self, _id: str) -> Session | None:
        return self._sessions.get(_id)

    async def create_session(self, user_id: UUID) -> Session:
        session = Session(user_id=user_id)
        self._sessions[session.id] = session
        return session

    async def delete_session(self, _id: str) -> None:
        try:
            self._sessions.pop(_id)
        except KeyError:
            logger.error(f"Session {_id} does not exist, so it cannot be deleted")


class RedisSessionStorage(AbstractSessionStorage):
    def __init__(self, redis: Redis, session_lifespan: timedelta = timedelta(days=1)) -> None:
        self.redis = redis
        self.lifespan = session_lifespan

    async def get_session(self, _id: str) -> Session | None:
        data = await self.redis.get(f"session:{_id}")
        logger.debug(f"{data}")
        if data is None:
            return None
        return Session(**data)

    async def create_session(self, user_id: UUID) -> Session:
        session = Session(user_id=user_id)
        await self.redis.setex(f"session:{session.id}", self.lifespan, session.user_id.bytes)
        logger.info(f"Created session {session.id} with lifespan {self.lifespan}")
        return session

    async def delete_session(self, _id: str) -> None:
        await self.redis.delete(f"session:{_id}")
        logger.info(f"Deleted session {id}")
