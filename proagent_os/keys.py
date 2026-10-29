"""Tenant API key mint, rotate, and revoke.

Hard cutover: rotate replaces the live secret in one transaction. The previous
key fails on the next request. There is no grace window.

Revoke stores an unusable placeholder and sets key_status to revoked. The
tenant cannot call the API again until an admin rotates that tenant.
Audit rows and logs store a short prefix and a SHA-256 fingerprint only.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
from typing import Any, Dict, Optional

from proagent_os.db import get_db, new_id, utcnow

logger = logging.getLogger("proagent.keys")

# One process, one writer. Stops two in-flight rotates from each returning a
# secret that the other request then overwrites. A second API worker has its own lock.
_mutation_lock = threading.Lock()

REVOKED_PREFIX = "revoked."
_PREFIX_LEN = 8

HARD_CUTOVER_DETAIL = "Previous key was invalidated immediately. No grace window."
REVOKE_RECOVERY = (
    "The tenant key no longer authenticates. An admin mints a replacement with "
    "POST /api/v1/tenants/{tenant_id}/api-key/rotate."
)


def mint_api_key() -> str:
    return f"pk_{secrets.token_urlsafe(24)}"


def key_prefix(api_key: str) -> str:
    """Short display prefix. Empty when the value is a placeholder or the whole secret."""
    if not api_key or api_key.startswith(REVOKED_PREFIX):
        return ""
    if len(api_key) <= _PREFIX_LEN:
        return ""
    return f"{api_key[:_PREFIX_LEN]}..."


def key_sha256(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_usable(row: Dict[str, Any]) -> bool:
    status = row.get("key_status") or "active"
    secret = str(row.get("api_key") or "")
    if status != "active":
        return False
    if not secret or secret.startswith(REVOKED_PREFIX):
        return False
    return True


def _fingerprints(api_key: Optional[str]) -> tuple[str, str]:
    if not api_key:
        return "", ""
    return key_prefix(api_key), key_sha256(api_key)


def _insert_audit(
    conn: Any,
    *,
    tenant_id: str,
    event: str,
    actor: str,
    prefix: str,
    digest: str,
    previous_prefix: str,
    previous_digest: str,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO tenant_api_key_audit (
            id, tenant_id, event, actor, key_prefix, key_sha256,
            previous_prefix, previous_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("aka"),
            tenant_id,
            event,
            actor,
            prefix,
            digest,
            previous_prefix,
            previous_digest,
            created_at,
        ),
    )


def log_key_action(
    *,
    event: str,
    tenant_id: str,
    actor: str,
    prefix: str,
    digest: str,
    previous_prefix: str = "",
) -> None:
    logger.info(
        "tenant_api_key event=%s tenant_id=%s actor=%s key_prefix=%s previous_prefix=%s key_fp=%s",
        event,
        tenant_id,
        actor,
        prefix,
        previous_prefix,
        (digest or "")[:12],
    )


def audit_issued(conn: Any, *, tenant_id: str, actor: str, api_key: str, created_at: str) -> tuple[str, str]:
    prefix, digest = _fingerprints(api_key)
    _insert_audit(
        conn,
        tenant_id=tenant_id,
        event="issued",
        actor=actor,
        prefix=prefix,
        digest=digest,
        previous_prefix="",
        previous_digest="",
        created_at=created_at,
    )
    return prefix, digest


def rotate_tenant_key(tenant_id: str, *, actor: str) -> Dict[str, Any]:
    with _mutation_lock:
        return _rotate_tenant_key(tenant_id, actor=actor)


def _rotate_tenant_key(tenant_id: str, *, actor: str) -> Dict[str, Any]:
    new_key = mint_api_key()
    now = utcnow()
    prefix, digest = _fingerprints(new_key)
    previous_prefix = ""
    with get_db().connect() as conn:
        row = conn.execute(
            "SELECT id, api_key, key_status FROM tenants WHERE id=?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            raise KeyError(tenant_id)
        previous = str(row["api_key"] or "")
        previous_status = row["key_status"] or "active"
        usable_previous = previous_status == "active" and not previous.startswith(REVOKED_PREFIX)
        previous_prefix, previous_digest = _fingerprints(previous) if usable_previous else ("", "")
        conn.execute(
            "UPDATE tenants SET api_key=?, key_status='active' WHERE id=?",
            (new_key, tenant_id),
        )
        _insert_audit(
            conn,
            tenant_id=tenant_id,
            event="rotated",
            actor=actor,
            prefix=prefix,
            digest=digest,
            previous_prefix=previous_prefix,
            previous_digest=previous_digest,
            created_at=now,
        )
    log_key_action(
        event="rotated",
        tenant_id=tenant_id,
        actor=actor,
        prefix=prefix,
        digest=digest,
        previous_prefix=previous_prefix,
    )
    return {
        "tenant_id": tenant_id,
        "api_key": new_key,
        "prefix": prefix,
        "previous_prefix": previous_prefix or None,
        "key_status": "active",
        "rotated_at": now,
        "detail": HARD_CUTOVER_DETAIL,
    }


def revoke_tenant_key(tenant_id: str, *, actor: str) -> Dict[str, Any]:
    with _mutation_lock:
        return _revoke_tenant_key(tenant_id, actor=actor)


def _revoke_tenant_key(tenant_id: str, *, actor: str) -> Dict[str, Any]:
    now = utcnow()
    with get_db().connect() as conn:
        row = conn.execute(
            "SELECT id, api_key, key_status FROM tenants WHERE id=?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            raise KeyError(tenant_id)
        if (row["key_status"] or "active") == "revoked":
            return {
                "tenant_id": tenant_id,
                "revoked": True,
                "already_revoked": True,
                "prefix": "",
                "key_status": "revoked",
                "revoked_at": now,
                "recovery": REVOKE_RECOVERY,
            }
        previous = str(row["api_key"] or "")
        prefix, digest = _fingerprints(previous)
        placeholder = f"{REVOKED_PREFIX}{secrets.token_urlsafe(24)}"
        conn.execute(
            "UPDATE tenants SET api_key=?, key_status='revoked' WHERE id=?",
            (placeholder, tenant_id),
        )
        _insert_audit(
            conn,
            tenant_id=tenant_id,
            event="revoked",
            actor=actor,
            prefix=prefix,
            digest=digest,
            previous_prefix="",
            previous_digest="",
            created_at=now,
        )
    log_key_action(
        event="revoked",
        tenant_id=tenant_id,
        actor=actor,
        prefix=prefix,
        digest=digest,
    )
    return {
        "tenant_id": tenant_id,
        "revoked": True,
        "already_revoked": False,
        "prefix": prefix,
        "key_status": "revoked",
        "revoked_at": now,
        "recovery": REVOKE_RECOVERY,
    }
