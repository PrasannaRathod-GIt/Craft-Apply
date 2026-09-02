from fastapi import Response

from app.core.config import settings


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = dict(
        httponly=True,
        secure=settings.COOKIE_SECURE,  # must be True in prod (Render/Vercel are https)
        samesite="none" if settings.COOKIE_SECURE else "lax",  # cross-site cookie needs None+Secure
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
    )
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **common,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
