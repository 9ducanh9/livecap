"""Cognito access-token validation for optional account features.

The MVP remains anonymous by default. Once ``ENABLE_AUTH`` is true, history
and export endpoints validate the caller's Cognito access token with
``cognito-idp:GetUser``. This delegates JWT signature, issuer, expiry, and
revocation checks to Cognito without putting a token parser or client secret in
the browser or container.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import base64
import json
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Header, HTTPException, status

from app.config import get_settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Minimal identity needed to partition transcript history."""

    user_id: str
    username: str
    email: str = ""


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        logger.warning("Cognito-protected request did not include an Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in is required to save or view transcript history",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        logger.warning("Cognito-protected request did not include a usable Bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Cognito bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def _belongs_to_configured_pool(token: str, *, region: str, user_pool_id: str) -> bool:
    """Pre-filter a JWT by issuer before Cognito performs full validation.

    Claims are not trusted here; ``GetUser`` below still verifies signature and
    expiry. This only prevents a valid access token from another pool in the
    same AWS account being accepted for this application's history partition.
    """

    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        expected = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        return claims.get("iss") == expected and claims.get("token_use") == "access"
    except (IndexError, UnicodeError, ValueError, json.JSONDecodeError):
        return False


@lru_cache(maxsize=1)
def _cognito_client(region: str):
    return boto3.client("cognito-idp", region_name=region)


def clear_auth_client_cache() -> None:
    """Clear the cached AWS client for isolated tests."""

    _cognito_client.cache_clear()


def authenticate_access_token(token: str) -> AuthenticatedUser:
    """Validate one Cognito access token and return its minimal identity."""

    settings = get_settings()
    if not settings.enable_auth or not settings.cognito_user_pool_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Accounts and transcript history are not enabled",
        )
    if not _belongs_to_configured_pool(
        token,
        region=settings.aws_region,
        user_pool_id=settings.cognito_user_pool_id,
    ):
        logger.warning("Cognito bearer token failed issuer or token-use validation")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The sign-in token is not valid for this LiveCap environment",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        response = _cognito_client(settings.aws_region).get_user(AccessToken=token)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "ClientError")
        logger.warning("Cognito GetUser rejected bearer token: %s", error_code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your sign-in session is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except BotoCoreError as exc:
        logger.warning("Cognito GetUser request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your sign-in session is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    username = str(response.get("Username", "")).strip()
    attributes = {
        str(attribute.get("Name", "")): str(attribute.get("Value", ""))
        for attribute in response.get("UserAttributes", [])
    }
    user_id = attributes.get("sub", "").strip() or username
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The sign-in session did not include a user identifier",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AuthenticatedUser(
        user_id=user_id,
        username=username or user_id,
        email=attributes.get("email", "").strip(),
    )


async def require_authenticated_user(
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    """Resolve the caller, or reject account-only features safely.

    This dependency intentionally rejects rather than silently falling back to
    anonymous history when the account feature has not been provisioned.
    """

    token = _bearer_token(authorization)
    return authenticate_access_token(token)


async def optional_authenticated_user(
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser | None:
    """Return no user while accounts are off; require one when they are on.

    Export remains backwards compatible for anonymous MVP deployments. After
    the account feature is enabled, an export must be attributable to its owner
    so it can safely appear in that owner's history.
    """

    if not get_settings().enable_auth:
        return None
    return await require_authenticated_user(authorization)
