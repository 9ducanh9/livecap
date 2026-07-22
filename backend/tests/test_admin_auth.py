"""Unit tests for require_admin_user: the Cognito "admin" group gate that
protects the admin dashboard on top of normal token validation.

Mocks the boto3 Cognito client directly (via app.services.auth._cognito_client)
rather than overriding FastAPI dependencies, since require_admin_user calls
require_authenticated_user as a plain function, not a Depends() sub-dependency
-- dependency_overrides can't intercept that call, only a real client mock can.
"""

from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from app.config import get_settings
from app.services import auth


@pytest.fixture(autouse=True)
def clear_caches():
    get_settings.cache_clear()
    auth.clear_auth_client_cache()
    yield
    get_settings.cache_clear()
    auth.clear_auth_client_cache()


def _fake_access_token(region: str, user_pool_id: str) -> str:
    """Build a JWT-shaped (but unsigned) token with the claims auth.py reads
    before ever calling Cognito: issuer and token_use. Signature validity is
    Cognito's job (GetUser, mocked below), not this pre-filter's.
    """

    def _b64(obj: dict) -> str:
        raw = json.dumps(obj).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    header = _b64({"alg": "RS256", "typ": "JWT"})
    payload = _b64({
        "iss": f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}",
        "token_use": "access",
    })
    return f"{header}.{payload}.fake-signature"


def _set_auth_env(monkeypatch):
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TESTPOOL")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


def test_require_admin_user_allows_admin_group_member(monkeypatch):
    _set_auth_env(monkeypatch)
    token = _fake_access_token("us-east-1", "us-east-1_TESTPOOL")

    fake_client = MagicMock()
    fake_client.get_user.return_value = {
        "Username": "user-1",
        "UserAttributes": [{"Name": "sub", "Value": "user-1"}, {"Name": "email", "Value": "a@x.com"}],
    }
    fake_client.admin_list_groups_for_user.return_value = {
        "Groups": [{"GroupName": "admin"}]
    }

    with patch.object(auth, "_cognito_client", return_value=fake_client):
        user = asyncio.run(auth.require_admin_user(authorization=f"Bearer {token}"))

    assert user.user_id == "user-1"
    fake_client.admin_list_groups_for_user.assert_called_once_with(
        Username="user-1", UserPoolId="us-east-1_TESTPOOL"
    )


def test_require_admin_user_rejects_non_admin(monkeypatch):
    _set_auth_env(monkeypatch)
    token = _fake_access_token("us-east-1", "us-east-1_TESTPOOL")

    fake_client = MagicMock()
    fake_client.get_user.return_value = {
        "Username": "user-2",
        "UserAttributes": [{"Name": "sub", "Value": "user-2"}],
    }
    fake_client.admin_list_groups_for_user.return_value = {
        "Groups": [{"GroupName": "beta-testers"}]
    }

    with patch.object(auth, "_cognito_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(auth.require_admin_user(authorization=f"Bearer {token}"))

    assert exc_info.value.status_code == 403


def test_require_admin_user_fails_closed_on_cognito_error(monkeypatch):
    _set_auth_env(monkeypatch)
    token = _fake_access_token("us-east-1", "us-east-1_TESTPOOL")

    fake_client = MagicMock()
    fake_client.get_user.return_value = {
        "Username": "user-3",
        "UserAttributes": [{"Name": "sub", "Value": "user-3"}],
    }
    fake_client.admin_list_groups_for_user.side_effect = ClientError(
        {"Error": {"Code": "InternalErrorException", "Message": "boom"}},
        "AdminListGroupsForUser",
    )

    with patch.object(auth, "_cognito_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(auth.require_admin_user(authorization=f"Bearer {token}"))

    # An AWS failure while checking admin status must never grant access.
    assert exc_info.value.status_code == 403


def test_require_admin_user_requires_a_token_first(monkeypatch):
    _set_auth_env(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth.require_admin_user(authorization=None))
    assert exc_info.value.status_code == 401
