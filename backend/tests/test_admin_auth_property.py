"""Property-based test for the admin authorization gate.

# Feature: admin-panel, Property 1: Admin authorization gate

**Validates: Requirements 1.1, 1.2, 1.3**

Property 1: For any request to any admin endpoint by a non-admin caller
(no token, invalid token, valid token for non-admin user), the API rejects
with 401 or 403 without executing endpoint logic.

Uses Hypothesis to generate different admin endpoints and caller scenarios,
verifying that the auth gate consistently blocks unauthorized access WITHOUT
the admin override dependency.
"""

from __future__ import annotations

import base64
import json
import os
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Test client setup — module-level, no fixture dependency from Hypothesis
# ---------------------------------------------------------------------------

# Set env vars before importing the app so auth is enabled. Saved so
# teardown_module can restore the process environment -- otherwise these
# leak into every test module collected afterward in the same pytest run
# (e.g. AWS_REGION="us-east-1" breaks moto-backed DynamoDB lookups in
# test_admin_service.py / test_stripe_billing.py / test_usage_quota_subscription.py).
_ENV_OVERRIDES = {
    "ENABLE_AUTH": "true",
    "COGNITO_USER_POOL_ID": "us-east-1_TESTPOOL",
    "AWS_REGION": "us-east-1",
}
_PREVIOUS_ENV = {key: os.environ.get(key) for key in _ENV_OVERRIDES}
os.environ.update(_ENV_OVERRIDES)

from app.config import get_settings  # noqa: E402
from app.services import auth  # noqa: E402

# Clear caches so env vars take effect
get_settings.cache_clear()
auth.clear_auth_client_cache()

from app.main import app  # noqa: E402

# Create a single TestClient for all property tests (no dependency overrides)
_client = TestClient(app, raise_server_exceptions=False)


def teardown_module(module):
    """Restore the process environment overridden above so later test
    modules in the same pytest run see the original ENABLE_AUTH/AWS_REGION
    values instead of this module's test-only overrides."""
    for key, previous in _PREVIOUS_ENV.items():
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
    get_settings.cache_clear()
    auth.clear_auth_client_cache()


def _fresh_client():
    """Return the module-level test client after clearing auth caches."""
    get_settings.cache_clear()
    auth.clear_auth_client_cache()
    return _client


# ---------------------------------------------------------------------------
# Admin endpoint definitions — all known admin API routes
# ---------------------------------------------------------------------------

ADMIN_GET_ENDPOINTS = [
    "/api/admin/overview",
    "/api/admin/users",
    "/api/admin/users/testuser123",
    "/api/admin/usage",
    "/api/admin/usage/top-users",
    "/api/admin/revenue",
    "/api/admin/system",
]

ADMIN_POST_ENDPOINTS = [
    "/api/admin/users/testuser123/disable",
    "/api/admin/users/testuser123/enable",
    "/api/admin/users/testuser123/reset-password",
]

# change-tier requires a JSON body
ADMIN_POST_WITH_BODY_ENDPOINTS = [
    ("/api/admin/users/testuser123/change-tier", {"tier": "pro"}),
]

ALL_ENDPOINTS = ADMIN_GET_ENDPOINTS + ADMIN_POST_ENDPOINTS


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy: pick any admin GET endpoint
admin_get_endpoint = st.sampled_from(ADMIN_GET_ENDPOINTS)

# Strategy: pick any admin POST endpoint (without body)
admin_post_endpoint = st.sampled_from(ADMIN_POST_ENDPOINTS)

# Strategy: pick any admin POST endpoint that needs a body
admin_post_body_endpoint = st.sampled_from(ADMIN_POST_WITH_BODY_ENDPOINTS)

# Strategy: generate invalid/garbage authorization header values
invalid_auth_headers = st.one_of(
    # No Authorization header at all
    st.just(None),
    # Empty string
    st.just(""),
    # Missing "Bearer" prefix — random text
    st.from_regex(r"[a-zA-Z0-9]{1,50}", fullmatch=True),
    # "Bearer" with no token
    st.just("Bearer "),
    # "Bearer" with garbage token (not valid JWT structure)
    st.from_regex(r"[a-zA-Z0-9]{1,80}", fullmatch=True).map(
        lambda s: f"Bearer {s}"
    ),
    # Wrong scheme
    st.from_regex(r"[a-zA-Z0-9]{1,50}", fullmatch=True).map(
        lambda s: f"Basic {s}"
    ),
    # Partial/malformed scheme
    st.just("Bear token123"),
)


def _build_headers(auth_value):
    """Build request headers from an authorization strategy value."""
    if auth_value is None:
        return {}
    return {"Authorization": auth_value}


def _fake_non_admin_token() -> str:
    """Build a fake JWT that passes the issuer pre-filter but represents
    a non-admin user."""
    def _b64(obj):
        raw = json.dumps(obj).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    header = _b64({"alg": "RS256", "typ": "JWT"})
    payload = _b64({
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TESTPOOL",
        "token_use": "access",
    })
    return f"{header}.{payload}.fake-signature"


# ---------------------------------------------------------------------------
# Property 1a: GET endpoints reject unauthenticated/invalid-token requests
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(endpoint=admin_get_endpoint, auth_header=invalid_auth_headers)
def test_get_endpoints_reject_unauthenticated(endpoint, auth_header):
    """For any admin GET endpoint and any non-admin caller (no token or
    invalid token), the API returns 401 or 403."""
    client = _fresh_client()
    headers = _build_headers(auth_header)
    response = client.get(endpoint, headers=headers)
    assert response.status_code in (401, 403), (
        f"Expected 401 or 403 for {endpoint} with auth={auth_header!r}, "
        f"got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Property 1b: POST endpoints reject unauthenticated/invalid-token requests
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(endpoint=admin_post_endpoint, auth_header=invalid_auth_headers)
def test_post_endpoints_reject_unauthenticated(endpoint, auth_header):
    """For any admin POST endpoint and any non-admin caller (no token or
    invalid token), the API returns 401 or 403."""
    client = _fresh_client()
    headers = _build_headers(auth_header)
    response = client.post(endpoint, headers=headers)
    assert response.status_code in (401, 403), (
        f"Expected 401 or 403 for {endpoint} with auth={auth_header!r}, "
        f"got {response.status_code}"
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    endpoint_body=admin_post_body_endpoint,
    auth_header=invalid_auth_headers,
)
def test_post_with_body_endpoints_reject_unauthenticated(endpoint_body, auth_header):
    """For any admin POST endpoint requiring a body and any non-admin caller,
    the API returns 401 or 403 (auth check fires before body validation)."""
    client = _fresh_client()
    endpoint, body = endpoint_body
    headers = _build_headers(auth_header)
    response = client.post(endpoint, json=body, headers=headers)
    assert response.status_code in (401, 403), (
        f"Expected 401 or 403 for {endpoint} with auth={auth_header!r}, "
        f"got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Property 1c: Valid token but non-admin user gets 403 on all endpoints
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    endpoint=st.sampled_from(ALL_ENDPOINTS),
)
def test_non_admin_user_gets_403(endpoint):
    """For any admin endpoint, a valid-token caller who is NOT in the admin
    group receives a 403 Forbidden response."""
    client = _fresh_client()

    # Mock Cognito to accept the token but return no admin group membership
    fake_client = MagicMock()
    fake_client.get_user.return_value = {
        "Username": "regular-user",
        "UserAttributes": [
            {"Name": "sub", "Value": "regular-user-sub-id"},
            {"Name": "email", "Value": "user@example.com"},
        ],
    }
    fake_client.admin_list_groups_for_user.return_value = {
        "Groups": [{"GroupName": "beta-testers"}]
    }

    fake_token = _fake_non_admin_token()
    headers = {"Authorization": f"Bearer {fake_token}"}

    with patch.object(auth, "_cognito_client", return_value=fake_client):
        if endpoint in ADMIN_POST_ENDPOINTS:
            response = client.post(endpoint, headers=headers)
        else:
            response = client.get(endpoint, headers=headers)

    assert response.status_code == 403, (
        f"Expected 403 for non-admin user on {endpoint}, "
        f"got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Property 1d: No endpoint logic executes when auth fails
# ---------------------------------------------------------------------------

@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(endpoint=st.sampled_from(ALL_ENDPOINTS))
def test_no_endpoint_logic_on_auth_failure(endpoint):
    """Verify that no downstream service calls (DynamoDB, Cognito admin ops,
    Stripe) happen when the auth gate rejects the request."""
    client = _fresh_client()

    with patch("app.services.admin_service.get_admin_overview") as mock_overview, \
         patch("app.services.admin_users.list_users") as mock_list, \
         patch("app.services.admin_users.get_user_detail") as mock_detail, \
         patch("app.services.admin_users.disable_user") as mock_disable, \
         patch("app.services.admin_users.enable_user") as mock_enable, \
         patch("app.services.admin_users.reset_password") as mock_reset, \
         patch("app.services.admin_analytics.get_monthly_usage") as mock_usage, \
         patch("app.services.admin_analytics.get_tier_distribution") as mock_tier, \
         patch("app.services.admin_analytics.get_top_users") as mock_top, \
         patch("app.services.admin_revenue.get_revenue_metrics") as mock_revenue, \
         patch("app.services.admin_health.get_system_health") as mock_health:

        # Make request with no auth header — should be rejected immediately
        if endpoint in ADMIN_POST_ENDPOINTS:
            response = client.post(endpoint)
        else:
            response = client.get(endpoint)

        # Auth should reject before any business logic runs
        assert response.status_code in (401, 403)

        # None of the service functions should have been called
        mock_overview.assert_not_called()
        mock_list.assert_not_called()
        mock_detail.assert_not_called()
        mock_disable.assert_not_called()
        mock_enable.assert_not_called()
        mock_reset.assert_not_called()
        mock_usage.assert_not_called()
        mock_tier.assert_not_called()
        mock_top.assert_not_called()
        mock_revenue.assert_not_called()
        mock_health.assert_not_called()
