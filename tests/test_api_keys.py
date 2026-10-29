"""Tenant API key rotate, revoke, and the in-process rate-limit stub."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3

import pytest

from proagent_os.config import get_settings
from proagent_os.db import get_db, reset_db, utcnow
from proagent_os.keys import key_prefix, key_sha256, mint_api_key
from proagent_os.ratelimit import reset_rate_limiter

ADMIN = {"Authorization": "Bearer test-admin-key"}


def _use(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    reset_rate_limiter()


def _client():
    from fastapi.testclient import TestClient

    from proagent_os.main import create_app

    return TestClient(create_app())


def _create(client, name: str = "Acme") -> dict:
    resp = client.post("/api/v1/tenants", headers=ADMIN, json={"name": name, "tone": "concise"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["api_key"].startswith("pk_")
    assert body["key_status"] == "active"
    return body


def _audits(tenant_id: str) -> list[dict]:
    return get_db().fetchall(
        "SELECT event, actor, key_prefix, key_sha256, previous_prefix, previous_sha256 "
        "FROM tenant_api_key_audit WHERE tenant_id=? ORDER BY rowid",
        (tenant_id,),
    )


def _assert_raw_key_hidden(secret: str, caplog: pytest.LogCaptureFixture) -> None:
    assert secret
    assert secret not in json.dumps(_all_audit_rows())
    messages = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("proagent.")
    )
    assert secret not in messages


def _all_audit_rows() -> list[dict]:
    return get_db().fetchall("SELECT * FROM tenant_api_key_audit")


def test_minted_prefix_is_not_the_secret():
    secret = mint_api_key()
    prefix = key_prefix(secret)
    assert prefix.endswith("...")
    assert secret not in prefix
    assert len(prefix) < len(secret)
    assert key_prefix("pk_short") == ""
    assert key_prefix("revoked.placeholder") == ""


def test_rotate_hard_cutover_hides_secret(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="proagent.keys")
    with _client() as client:
        created = _create(client, "Rotate Co")
        tid = created["id"]
        old = created["api_key"]
        me = client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {old}"})
        assert me.status_code == 200
        assert me.json()["api_key"] == old

        admin_self = client.post("/api/v1/tenants/me/api-key/rotate", headers=ADMIN)
        assert admin_self.status_code == 400

        other = client.post(f"/api/v1/tenants/{tid}/api-key/rotate", headers={"Authorization": f"Bearer {old}"})
        assert other.status_code == 403
        assert client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {old}"}).status_code == 200

        rotated = client.post("/api/v1/tenants/me/api-key/rotate", headers={"Authorization": f"Bearer {old}"})
        assert rotated.status_code == 200, rotated.text
        body = rotated.json()
        new = body["api_key"]
        assert new != old
        assert body["key_status"] == "active"
        assert body["prefix"] == key_prefix(new)
        assert body["previous_prefix"] == key_prefix(old)
        assert "No grace window" in body["detail"]
        assert old not in rotated.text

        stale = client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {old}"})
        assert stale.status_code == 401
        assert stale.json()["detail"] == "Invalid API key"

        fresh = client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {new}"})
        assert fresh.status_code == 200
        assert fresh.json()["api_key"] == new
        assert fresh.json()["key_status"] == "active"

        missing = client.post("/api/v1/tenants/ten_missing/api-key/rotate", headers=ADMIN)
        assert missing.status_code == 404

    audits = _audits(tid)
    assert [row["event"] for row in audits] == ["issued", "rotated"]
    assert audits[0]["actor"] == "admin"
    assert audits[1]["actor"] == tid
    assert audits[1]["key_sha256"] == key_sha256(new)
    assert audits[1]["previous_sha256"] == hashlib.sha256(old.encode()).hexdigest()
    _assert_raw_key_hidden(old, caplog)
    _assert_raw_key_hidden(new, caplog)
    assert "tenant_api_key event=rotated" in caplog.text
    assert key_prefix(new) in caplog.text


def test_revoke_requires_admin_reissue(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="proagent.keys")
    with _client() as client:
        created = _create(client, "Revoke Co")
        tid = created["id"]
        old = created["api_key"]
        headers = {"Authorization": f"Bearer {old}"}

        revoked = client.post("/api/v1/tenants/me/api-key/revoke", headers=headers)
        assert revoked.status_code == 200, revoked.text
        body = revoked.json()
        assert body["revoked"] is True
        assert body["already_revoked"] is False
        assert body["key_status"] == "revoked"
        assert body["prefix"] == key_prefix(old)
        assert "api-key/rotate" in body["recovery"]
        assert old not in revoked.text

        dead = client.get("/api/v1/tenants/me", headers=headers)
        assert dead.status_code == 401
        self_rotate = client.post("/api/v1/tenants/me/api-key/rotate", headers=headers)
        assert self_rotate.status_code == 401

        listed = client.get("/api/v1/tenants", headers=ADMIN)
        assert listed.status_code == 200
        row = next(item for item in listed.json() if item["id"] == tid)
        assert row["key_status"] == "revoked"
        assert "api_key" not in row
        assert old not in listed.text

        stored = get_db().fetchone("SELECT api_key, key_status FROM tenants WHERE id=?", (tid,))
        assert stored["key_status"] == "revoked"
        assert stored["api_key"].startswith("revoked.")
        assert stored["api_key"] not in revoked.text
        assert stored["api_key"] not in listed.text
        assert stored["api_key"] not in caplog.text

        again = client.post(f"/api/v1/tenants/{tid}/api-key/revoke", headers=ADMIN)
        assert again.status_code == 200
        assert again.json()["already_revoked"] is True

        reissued = client.post(f"/api/v1/tenants/{tid}/api-key/rotate", headers=ADMIN)
        assert reissued.status_code == 200, reissued.text
        new = reissued.json()["api_key"]
        assert new.startswith("pk_")
        assert reissued.json()["previous_prefix"] is None
        assert client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {new}"}).status_code == 200
        assert client.get("/api/v1/tenants/me", headers=headers).status_code == 401
        assert client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {stored['api_key']}"}).status_code == 401

    events = [row["event"] for row in _audits(tid)]
    assert events == ["issued", "revoked", "rotated"]
    _assert_raw_key_hidden(old, caplog)
    _assert_raw_key_hidden(new, caplog)
    _assert_raw_key_hidden(stored["api_key"], caplog)
    assert "tenant_api_key event=revoked" in caplog.text


def test_rate_limit_429_is_per_tenant(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch):
    caplog.set_level(logging.INFO, logger="proagent.ratelimit")
    _use(
        monkeypatch,
        PROAGENT_RATE_LIMIT_ENABLED="true",
        PROAGENT_RATE_LIMIT_REQUESTS="2",
        PROAGENT_RATE_LIMIT_WINDOW_SECONDS="60",
    )
    with _client() as client:
        first = _create(client, "Limited A")
        second = _create(client, "Limited B")
        blocked = client.get("/api/v1/tenants", headers=ADMIN)
        assert blocked.status_code == 429
        assert blocked.json() == {"detail": "Rate limit exceeded"}
        assert int(blocked.headers["retry-after"]) >= 1
        assert blocked.headers["x-ratelimit-remaining"] == "0"
        assert blocked.headers["x-ratelimit-limit"] == "2"

        health = client.get("/health")
        assert health.status_code == 200
        assert "x-ratelimit-limit" not in health.headers

        key = first["api_key"]
        headers = {"Authorization": f"Bearer {key}"}
        ok1 = client.get("/api/v1/tenants/me", headers=headers)
        ok2 = client.get("/api/v1/tenants/me", headers=headers)
        assert ok1.status_code == 200
        assert ok2.status_code == 200
        assert ok1.headers["x-ratelimit-limit"] == "2"
        assert ok2.headers["x-ratelimit-remaining"] == "0"
        limited = client.get("/api/v1/tenants/me", headers=headers)
        assert limited.status_code == 429
        assert limited.json()["detail"] == "Rate limit exceeded"
        messages = "\n".join(record.getMessage() for record in caplog.records)
        assert key not in messages
        assert second["api_key"] not in messages

        # The other tenant still has its own bucket.
        other = client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {second['api_key']}"})
        assert other.status_code == 200


def test_rate_limit_can_be_disabled(monkeypatch: pytest.MonkeyPatch):
    _use(
        monkeypatch,
        PROAGENT_RATE_LIMIT_ENABLED="false",
        PROAGENT_RATE_LIMIT_REQUESTS="1",
        PROAGENT_RATE_LIMIT_WINDOW_SECONDS="60",
    )
    with _client() as client:
        first = _create(client, "Unlimited A")
        second = _create(client, "Unlimited B")
        third = client.get("/api/v1/tenants", headers=ADMIN)
        assert first["id"] != second["id"]
        assert third.status_code == 200
        assert "x-ratelimit-limit" not in third.headers


def test_legacy_tenant_table_migrates_and_rotates():
    path_row = get_db().path
    legacy = path_row.parent / "legacy.db"
    secret = "pk_legacy_secret_value_ok"
    conn = sqlite3.connect(legacy)
    conn.execute(
        """
        CREATE TABLE tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key TEXT NOT NULL UNIQUE,
            goals TEXT DEFAULT '',
            constraints TEXT DEFAULT '',
            tone TEXT DEFAULT 'professional',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO tenants (id, name, api_key, goals, constraints, tone, created_at) VALUES (?, ?, ?, '', '', 'professional', ?)",
        ("ten_legacy", "Legacy Co", secret, utcnow()),
    )
    conn.commit()
    conn.close()

    reset_db(legacy)
    status = get_db().fetchone("SELECT key_status, api_key FROM tenants WHERE id=?", ("ten_legacy",))
    assert status["key_status"] == "active"
    assert status["api_key"] == secret

    with _client() as client:
        me = client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {secret}"})
        assert me.status_code == 200
        assert me.json()["id"] == "ten_legacy"
        rotated = client.post(
            "/api/v1/tenants/me/api-key/rotate",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert rotated.status_code == 200
        new = rotated.json()["api_key"]
        assert client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {secret}"}).status_code == 401
        assert client.get("/api/v1/tenants/me", headers={"Authorization": f"Bearer {new}"}).status_code == 200
