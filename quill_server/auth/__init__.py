from typing import Annotated
from uuid import UUID

from fastapi import HTTPException, Header, WebSocketException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from passlib.hash import argon2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quill_server.db.models import User
from quill_server.schema import TokenResponse
from quill_server.db.connect import get_db
from quill_server.cache import client
from quill_server.config import settings
from quill_server.auth.store import RedisSessionStorage, InMemorySessionStorage
from quill_server.auth.session import Session

oauth2 = OAuth2PasswordBearer(tokenUrl="user/token")

if settings.USE_REDIS_SESSIONS:
    sessions = RedisSessionStorage(redis=client)
    logger.info(f"Using RedisSessionStorage - sessions expire in {sessions.lifespan}")
else:
    logger.warning(
        "Using InMemorySessionStorage - these sessions do NOT expire."
        " Set the USE_REDIS_SESSIONS env var to True to use the redis backend"
        " for storing sessions."
    )
    sessions = InMemorySessionStorage()


async def set_session(user_id: UUID, token_type: str = "bearer") -> TokenResponse:
    session = await sessions.create_session(user_id)
    return TokenResponse(access_token=session.id, token_type=token_type)


async def get_current_session_ws(authorization: Annotated[str, Header()]) -> Session:
    bearer, token = authorization.split()
    session = await sessions.get_session(token)
    if not session:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return session


async def get_current_user_ws(
    session: Annotated[Session, Depends(get_current_session_ws)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    stmt = select(User).where(User.id == session.user_id)
    async with db.begin():
        user = await db.execute(stmt)
    return user.scalar_one()


async def get_current_session(token: Annotated[str, Depends(oauth2)]) -> Session:
    session = await sessions.get_session(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session


async def delete_session(_id: str) -> None:
    await sessions.delete_session(_id)


async def get_current_user(
    session: Annotated[Session, Depends(get_current_session)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    stmt = select(User).where(User.id == session.user_id)
    async with db.begin():
        user = await db.execute(stmt)
    return user.scalar_one()


def hash_password(pw: str) -> str:
    return argon2.using(rounds=4).hash(pw)


def verify_password(plain: str, hashed: str) -> bool:
    return argon2.verify(plain, hashed)
