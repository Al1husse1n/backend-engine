from __future__ import annotations

from fastapi import Depends, Header
from jose import JWTError, jwt

from app.config import settings
from app.errors import AuthenticationFailed


def get_authenticated_user_id(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """Validate Supabase Bearer token and extract user id from 'sub' claim."""
    if not authorization:
        raise AuthenticationFailed("Authorization header is required.")

    if not authorization.startswith("Bearer "):
        raise AuthenticationFailed("Authorization header must be in 'Bearer <token>' format.")

    token = authorization[7:].strip()
    if not token:
        raise AuthenticationFailed("Authentication token is missing.")

    secret = settings.supabase_jwt_secret.strip()
    if not secret:
        raise AuthenticationFailed("Authentication secret is not configured.")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False,
            },
        )
    except JWTError:
        raise AuthenticationFailed("Invalid or expired authentication token.")

    sub = payload.get("sub")
    if not sub or not isinstance(sub, str) or not sub.strip():
        raise AuthenticationFailed("Token subject claim is missing or invalid.")

    return sub.strip()


def get_authenticated_business_id(
    user_id: str = Depends(get_authenticated_user_id),
) -> str:
    """Derive isolated business identity from the authenticated user ID."""
    return f"biz_{user_id}"
