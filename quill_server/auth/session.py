import base64
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


def _get_token() -> str:
    """Make a session token based on a UUID"""
    return base64.b64encode(uuid4().bytes).decode("utf-8")


class Session(BaseModel):
    """A user session.

    Whenever a user logs in successfully, a Session object
    is created and stored in a session storage backend.
    """

    id: str = Field(default_factory=_get_token)  # noqa: A003
    user_id: UUID
