"""Pydantic models for request and response validation."""
from pydantic import BaseModel


class UserSignupBody(BaseModel):
    username: str
    password: str


class MessageResponse(BaseModel):
    message: str
