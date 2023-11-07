from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from quill_server.auth import hash_password
from quill_server.db.connect import get_db
from quill_server.db.models import User
from quill_server.schema import MessageResponse, UserSignupBody


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
