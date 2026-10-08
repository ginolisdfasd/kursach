"""Авторизация по сессионной куке: имя пользователя, подписанное HMAC."""
import hashlib
import hmac

from fastapi import HTTPException, Request

from . import config, repo

COOKIE = "session"


def hash_password(password: str) -> str:
    return hashlib.sha256(("library:" + password).encode()).hexdigest()


def sign(username: str) -> str:
    mac = hmac.new(config.SECRET_KEY.encode(), username.encode(), hashlib.sha256).hexdigest()
    return f"{username}:{mac}"


def check_credentials(username: str, password: str):
    user = repo.get_user_by_name(username)
    if user and hmac.compare_digest(user["password_hash"], hash_password(password)):
        return user
    return None


def current_user(request: Request):
    raw = request.cookies.get(COOKIE, "")
    username, _, mac = raw.partition(":")
    if not username or not hmac.compare_digest(sign(username), raw):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    user = repo.get_user_by_name(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user
