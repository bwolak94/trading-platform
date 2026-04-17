"""Authentication utilities: JWT creation, validation, and FastAPI dependencies."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Configurable token lifetime (default 24 hours)
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

JWT_ALGORITHM = "HS256"

_bearer_scheme = HTTPBearer(auto_error=False)

# Default dev user returned when ENVIRONMENT == "development" and no token is provided
_DEV_USER: dict[str, str] = {
    "sub": "dev-user-000",
    "role": "admin",
}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token.

    Args:
        data: Claims to encode in the token. Must include at least ``sub``.
        expires_delta: Optional custom expiration. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.now(timezone.utc)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Raises:
        HTTPException: 401 if the token is expired, invalid, or missing required claims.
    """
    try:
        payload: dict = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency that extracts and validates the current user from a Bearer token.

    Returns:
        A dict with at least ``sub`` (user id) and ``role`` keys.

    Raises:
        HTTPException: 401 if no token is provided or the token is invalid.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_token(credentials.credentials)

    return {
        "sub": payload["sub"],
        "role": payload.get("role", "user"),
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[dict]:
    """FastAPI dependency that returns the current user or ``None``.

    In development mode (``ENVIRONMENT == 'development'``), always returns a
    default dev user when no token is provided, so that frontend development
    does not require authentication.
    """
    if credentials is None or not credentials.credentials:
        if settings.ENVIRONMENT == "development":
            return _DEV_USER
        return None

    try:
        payload = _decode_token(credentials.credentials)
        return {
            "sub": payload["sub"],
            "role": payload.get("role", "user"),
        }
    except HTTPException:
        # In development, fall back to dev user even on invalid tokens
        if settings.ENVIRONMENT == "development":
            logger.debug("Invalid token in dev mode; returning default dev user")
            return _DEV_USER
        return None
