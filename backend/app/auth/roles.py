"""Role-Based Access Control — multi-user permission system.

Defines three user roles with escalating permissions:
- VIEWER: Read-only access to signals and market data
- ANALYST: Can run backtests and configure strategies
- ADMIN: Full access including user management and system configuration

Designed for future SaaS monetization with tenant isolation.
"""

from __future__ import annotations

import secrets
import time
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class UserRole(str, Enum):
    """User role enumeration."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


# Permission definitions per role
ROLE_PERMISSIONS: dict[UserRole, list[str]] = {
    UserRole.ADMIN: [
        "read",
        "write",
        "delete",
        "manage_users",
        "configure_strategies",
        "run_backtest",
        "manage_alerts",
        "view_analytics",
        "export_data",
        "manage_webhooks",
    ],
    UserRole.ANALYST: [
        "read",
        "write",
        "run_backtest",
        "configure_strategies",
        "manage_alerts",
        "view_analytics",
    ],
    UserRole.VIEWER: [
        "read",
        "view_analytics",
    ],
}


def has_permission(role: UserRole, permission: str) -> bool:
    """Check if a role has a specific permission.

    Args:
        role: User role enum value
        permission: Permission string to check

    Returns:
        True if the role has the requested permission
    """
    return permission in ROLE_PERMISSIONS.get(role, [])


def require_permission(permission: str):
    """FastAPI dependency factory for permission-based access control.

    Args:
        permission: Required permission string

    Returns:
        FastAPI dependency function
    """
    async def _check_permission(role: str = "viewer") -> None:
        try:
            user_role = UserRole(role)
        except ValueError:
            raise HTTPException(status_code=403, detail=f"Invalid role: {role}")

        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' required. Your role: {role}",
            )

    return Depends(_check_permission)


class UserSession:
    """In-memory session management for multi-user support.

    Stores active sessions with role assignments. In production,
    this should be replaced with Redis or database-backed sessions.
    """

    _SESSION_TTL = 86400  # 24 hours

    def __init__(self) -> None:
        """Initialize with empty session store."""
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self, user_id: str, role: UserRole) -> str:
        """Create a new authenticated session.

        Args:
            user_id: Unique user identifier
            role: Assigned user role

        Returns:
            Session token string (URL-safe, 32 bytes)
        """
        token = secrets.token_urlsafe(32)
        self._sessions[token] = {
            "user_id": user_id,
            "role": role.value,
            "created_at": time.time(),
            "last_seen": time.time(),
        }
        logger.info("Session created for user %s (role: %s)", user_id, role.value)
        return token

    def validate_session(self, token: str) -> dict[str, Any] | None:
        """Validate a session token and update last-seen timestamp.

        Args:
            token: Session token to validate

        Returns:
            Session data dict if valid, None if expired or not found
        """
        session = self._sessions.get(token)
        if not session:
            return None

        # Check TTL
        if time.time() - session["created_at"] > self._SESSION_TTL:
            del self._sessions[token]
            return None

        session["last_seen"] = time.time()
        return dict(session)

    def revoke_session(self, token: str) -> bool:
        """Revoke a session immediately.

        Args:
            token: Session token to revoke

        Returns:
            True if session was found and revoked
        """
        if token in self._sessions:
            user_id = self._sessions[token].get("user_id")
            del self._sessions[token]
            logger.info("Session revoked for user %s", user_id)
            return True
        return False

    def get_active_sessions(self) -> list[dict[str, Any]]:
        """Return all non-expired sessions (without tokens for security).

        Returns:
            List of session info dicts
        """
        now = time.time()
        active = []
        expired_tokens = []

        for token, session in self._sessions.items():
            if now - session["created_at"] > self._SESSION_TTL:
                expired_tokens.append(token)
                continue
            active.append({
                "user_id": session["user_id"],
                "role": session["role"],
                "created_at": session["created_at"],
                "last_seen": session["last_seen"],
                "age_hours": round((now - session["created_at"]) / 3600, 1),
            })

        # Clean up expired sessions
        for token in expired_tokens:
            del self._sessions[token]

        return active

    def get_role_summary(self) -> dict[str, Any]:
        """Return role permission summary for documentation.

        Returns:
            Dict of role -> permissions
        """
        return {
            role.value: perms
            for role, perms in ROLE_PERMISSIONS.items()
        }


# Module-level singleton
_session_manager: UserSession | None = None


def get_session_manager() -> UserSession:
    """Return the global UserSession singleton.

    Returns:
        Shared UserSession instance
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = UserSession()
    return _session_manager
