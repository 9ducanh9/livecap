"""Unit coverage for optional Cognito ownership and transcript history."""

from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient
from moto import mock_aws

from app.main import app
from app.routers import history as history_router
from app.services.auth import AuthenticatedUser, _belongs_to_configured_pool, require_authenticated_user
from app.services.storage import generate_s3_object_key
from app.services.transcript_history import list_history_records, save_history_record


def _unsigned_token(claims: dict[str, str]) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def test_token_pool_prefilter_accepts_expected_access_token() -> None:
    token = _unsigned_token(
        {
            "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_example",
            "token_use": "access",
        }
    )
    assert _belongs_to_configured_pool(
        token, region="ap-southeast-1", user_pool_id="ap-southeast-1_example"
    )
    assert not _belongs_to_configured_pool(
        token, region="ap-southeast-1", user_pool_id="ap-southeast-1_other"
    )


def test_owner_export_key_stays_under_a_user_prefix() -> None:
    key = generate_s3_object_key("session-a", owner_id="user-a")
    assert key.startswith("transcripts/users/user-a/session-a/")


@mock_aws
def test_history_records_are_partitioned_by_user() -> None:
    import boto3

    client = boto3.client("dynamodb", region_name="ap-southeast-1")
    client.create_table(
        TableName="history",
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "history_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "history_id", "AttributeType": "S"},
        ],
    )
    save_history_record(
        table_name="history", region="ap-southeast-1", user_id="user-a",
        session_id="session-a", s3_key="transcripts/a.txt", segment_count=2,
        retention_days=14, client=client,
    )
    save_history_record(
        table_name="history", region="ap-southeast-1", user_id="user-b",
        session_id="session-b", s3_key="transcripts/b.txt", segment_count=3,
        retention_days=14, client=client,
    )
    records = list_history_records(
        table_name="history", region="ap-southeast-1", user_id="user-a", limit=20, client=client
    )
    assert [record.session_id for record in records] == ["session-a"]


def test_history_endpoint_returns_only_authenticated_users_records(monkeypatch) -> None:
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser("user-a", "user-a")
    monkeypatch.setattr(
        history_router,
        "list_history_records",
        lambda **_: [
            type("Record", (), {
                "history_id": "2026-01-01#session-a", "session_id": "session-a",
                "segment_count": 2, "created_at": __import__("datetime").datetime(2026, 1, 1),
            })()
        ],
    )
    try:
        response = TestClient(app).get("/api/transcripts")
        assert response.status_code == 200
        assert response.json()["items"][0]["session_id"] == "session-a"
    finally:
        app.dependency_overrides.clear()
