from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from quill_server.auth import get_current_user
from quill_server.db.models import User
from quill_server.schema import CreateRoomResponse


router = APIRouter(prefix="/room")


# ruff complains about the Path() call, but this is FastAPI convention
async def get_current_room(room_id: UUID = Path(...)) -> ...:  # noqa: B008
    ...


@router.post("/")
async def create_room(user: Annotated[User, Depends(get_current_user)]) -> CreateRoomResponse:
    ...
