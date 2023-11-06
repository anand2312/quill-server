"""Pydantic models for request and response validation."""
from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str
