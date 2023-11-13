from typing import Annotated
from fastapi import APIRouter, Depends
from quill_server.auth import get_current_user

from quill_server.db.models import User
from quill_server.schema import CreateRoomResponse


router = APIRouter(prefix="/room")


@router.post("/")
async def create_room(user: Annotated[User, Depends(get_current_user)]) -> CreateRoomResponse:
    ...
