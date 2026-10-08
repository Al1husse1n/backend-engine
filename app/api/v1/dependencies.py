from __future__ import annotations

import time
from typing import Any

from fastapi import Depends, Header
import httpx
from jose import JWTError, jwk, jwt

from app.config import settings
from app.errors import AuthenticationFailed


class JWKSCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._keys_by_kid: dict[str, dict[str, Any]] = {}
        self._last_fetched: float = 0.0

    def clear(self) -> None:
        self._keys_by_kid = {}
        self._last_fetched = 0.0

    def get_signing_key(self, jwks_url: str, kid: str) -> dict[str, Any] | None:
        now = time.time()
        # If key is cached and TTL hasn't expired, use it
        if kid in self._keys_by_kid and (now - self._last_fetched) < self.ttl_seconds:
            return self._keys_by_kid[kid]

        # Refresh from JWKS endpoint (handles rotation or initial/expired fetch)
        self.fetch_and_cache_keys(jwks_url)
        return self._keys_by_kid.get(kid)

    def fetch_and_cache_keys(self, jwks_url: str) -> None:
        try:
            data = fetch_jwks(jwks_url)
        except AuthenticationFailed:
            raise
        except Exception as exc:
            raise AuthenticationFailed("Authentication service is temporarily unavailable.") from exc

        if not isinstance(data, dict):
            raise AuthenticationFailed("Invalid JWKS response from authentication provider.")

        keys = data.get("keys", [])
        if not isinstance(keys, list):
            raise AuthenticationFailed("Invalid JWKS response from authentication provider.")

        keys_by_kid: dict[str, dict[str, Any]] = {}
        for key in keys:
            if isinstance(key, dict) and isinstance(key.get("kid"), str) and key["kid"].strip():
                keys_by_kid[key["kid"].strip()] = key

        self._keys_by_kid = keys_by_kid
        self._last_fetched = time.time()


def fetch_jwks(jwks_url: str) -> dict[str, Any]:
    """Fetch the JWKS document from the provider's endpoint."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(jwks_url)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise AuthenticationFailed("Authentication service is temporarily unavailable.") from exc


jwks_cache = JWKSCache()


def get_authenticated_user_id(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """Validate Supabase Bearer token using ES256 and the project's JWKS endpoint."""
    if not authorization:
        raise AuthenticationFailed("Authorization header is required.")

    if not authorization.startswith("Bearer "):
        raise AuthenticationFailed("Authorization header must be in 'Bearer <token>' format.")

    token = authorization[7:].strip()
    if not token:
        raise AuthenticationFailed("Authentication token is missing.")

    supabase_url = settings.supabase_url.strip().rstrip("/")
    if not supabase_url:
        raise AuthenticationFailed("Authentication service is not configured.")

    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    expected_issuer = f"{supabase_url}/auth/v1"

    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise AuthenticationFailed("Invalid or expired authentication token.")

    alg = header.get("alg")
    if alg != "ES256":
        raise AuthenticationFailed("Invalid or expired authentication token.")

    kid = header.get("kid")
    if not kid or not isinstance(kid, str) or not kid.strip():
        raise AuthenticationFailed("Invalid or expired authentication token.")
    kid = kid.strip()

    key_dict = jwks_cache.get_signing_key(jwks_url, kid)
    if not key_dict:
        raise AuthenticationFailed("Invalid or expired authentication token.")

    if key_dict.get("kty") != "EC" or key_dict.get("crv") != "P-256":
        raise AuthenticationFailed("Invalid or expired authentication token.")

    try:
        key = jwk.construct(key_dict, algorithm="ES256")
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            issuer=expected_issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": False,
            },
        )
    except (JWTError, ValueError):
        raise AuthenticationFailed("Invalid or expired authentication token.")

    if not isinstance(payload, dict):
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
