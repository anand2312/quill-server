from fastapi.security import OAuth2PasswordBearer
from passlib.hash import argon2


oauth2 = OAuth2PasswordBearer(tokenUrl="user/token")


def hash_password(pw: str) -> str:
    return argon2.using(rounds=4).hash(pw)


def verify_password(plain: str, hashed: str) -> bool:
    return argon2.verify(plain, hashed)
