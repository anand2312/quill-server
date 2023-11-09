"""Pydantic models for request and response validation."""
from pydantic import BaseModel


class UserSignupBody(BaseModel):
    username: str
    password: str


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
