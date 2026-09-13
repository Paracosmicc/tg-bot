import time
import secrets
from collections import defaultdict
from fastapi import Header, HTTPException, status, Request
from typing import Optional
from config import DASHBOARD_PASSWORD
import db

# In-memory IP-based rate limiting for login attempts
_failed_attempts: dict[str, list[float]] = defaultdict(list)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes lockout


def check_login_rate_limit(client_ip: str):
    """Check and enforce brute-force rate limit per IP."""
    now = time.time()
    attempts = [t for t in _failed_attempts[client_ip] if now - t < LOCKOUT_WINDOW_SECONDS]
    _failed_attempts[client_ip] = attempts

    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        retry_after = int(LOCKOUT_WINDOW_SECONDS - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Temporarily locked out. Try again in {max(1, retry_after)} seconds.",
            headers={"Retry-After": str(max(1, retry_after))},
        )


def record_failed_login(client_ip: str):
    """Record a failed login attempt."""
    _failed_attempts[client_ip].append(time.time())


def reset_login_attempts(client_ip: str):
    """Reset failed attempts on successful authentication."""
    if client_ip in _failed_attempts:
        del _failed_attempts[client_ip]


def get_token_from_header(
    authorization: Optional[str] = Header(None),
    x_admin_password: Optional[str] = Header(None),
) -> Optional[str]:
    """Extract token string from Authorization or X-Admin-Password header."""
    if authorization:
        if authorization.startswith("Bearer "):
            return authorization.split("Bearer ", 1)[1].strip()
        return authorization.strip()
    if x_admin_password:
        return x_admin_password.strip()
    return None


async def verify_admin(
    authorization: Optional[str] = Header(None),
    x_admin_password: Optional[str] = Header(None),
) -> str:
    """
    Validates admin credentials via session token or master dashboard password.
    Returns the authenticated token.
    """
    token = get_token_from_header(authorization, x_admin_password)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Check if token is an active session in MongoDB
    is_valid_session, session_doc = await db.validate_admin_session(token)
    if is_valid_session:
        return token

    # 2. Check if token is master DASHBOARD_PASSWORD using constant-time comparison
    if secrets.compare_digest(token, DASHBOARD_PASSWORD):
        return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Session expired or revoked. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

