from fastapi import Header, HTTPException, status
from typing import Optional
from config import DASHBOARD_PASSWORD


async def verify_admin(
    authorization: Optional[str] = Header(None),
    x_admin_password: Optional[str] = Header(None),
):
    """
    Validates admin credentials via Bearer token or X-Admin-Password header.
    """
    token = None
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization.split("Bearer ", 1)[1].strip()
        else:
            token = authorization.strip()
    elif x_admin_password:
        token = x_admin_password.strip()

    if not token or token != DASHBOARD_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid dashboard password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
