from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from quill_server.auth import hash_password, set_session, verify_password
from quill_server.db.connect import get_db
from quill_server.db.models import User
from quill_server.schema import MessageResponse, TokenResponse, UserSignupBody


router = APIRouter(prefix="/user", tags=["user"])


@router.post("/signup")
async def signup(
    user: UserSignupBody, session: Annotated[AsyncSession, Depends(get_db)]
) -> MessageResponse:
    try:
        async with session.begin():
            session.add(User(username=user.username, password=hash_password(user.password)))
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Username is already in used") from e
    logger.info(f"Created new user {user.username}")
    return MessageResponse(message="User signed up succesfully")


@router.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    username = form_data.username
    plaintext = form_data.password
    async with db.begin():
        res = await db.execute(select(User).where(User.username == username))
    user = res.scalar_one_or_none()
    if not user:
        logger.info(f"Attempted logging in user - {username} that does not exist")
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(plaintext, user.password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    session = await set_session(user.id)
    return session
