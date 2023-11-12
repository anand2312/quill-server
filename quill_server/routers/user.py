from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from quill_server.auth import get_current_user, hash_password, set_session, verify_password
from quill_server.db.connect import get_db
from quill_server.db.models import User
from quill_server.schema import MessageResponse, SuccessfulLoginResponse, UserSignupBody


router = APIRouter(prefix="/user", tags=["user"])


@router.post("/signup")
async def signup(
    user: UserSignupBody, session: Annotated[AsyncSession, Depends(get_db)]
) -> SuccessfulLoginResponse:
    try:
        async with session.begin():
            db_user = User(username=user.username, password=hash_password(user.password))
            session.add(db_user)
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Username is already in use") from e
    logger.info(f"Created new user {user.username}")
    user_session = await set_session(db_user.id)
    return SuccessfulLoginResponse(username=db_user.username, token=user_session)


@router.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessfulLoginResponse:
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
    return SuccessfulLoginResponse(username=username, token=session)


@router.get("/loggedin")
async def test_logged_in(user: Annotated[User, Depends(get_current_user)]) -> MessageResponse:
    return MessageResponse(message=f"Hello {user.username}!")
