"""
Wraps whatever get_current_user() you built in Phase 1's auth step.
Assumes the returned user object has an `is_admin` boolean attribute
(matching your Flask `user["is_admin"] != 1` check). If your User model
uses a role string instead, swap the check accordingly.
"""
from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user


async def require_admin(user=Depends(get_current_user)):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user