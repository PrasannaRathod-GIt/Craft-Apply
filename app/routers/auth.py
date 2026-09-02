from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest, UserOut

router = APIRouter(tags=["auth"])

# ---- Google OAuth client setup (mirrors your Authlib Flask registration) ----
oauth = OAuth()
if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


@router.post("/api/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if await _get_user_by_email(db, payload.email.lower()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already used")

    user = User(
        email=payload.email.lower(),
        username=payload.username,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    set_auth_cookies(response, create_access_token(user.id), create_refresh_token(user.id))
    return AuthResponse(message="Signed up successfully", user=UserOut.model_validate(user))


@router.post("/api/login", response_model=AuthResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await _get_user_by_email(db, payload.email.lower())
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not registered")
    if not user.password_hash:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account uses Google login only")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password incorrect")

    set_auth_cookies(response, create_access_token(user.id), create_refresh_token(user.id))
    return AuthResponse(message="Logged in", user=UserOut.model_validate(user))


@router.post("/api/refresh", response_model=AuthResponse)
async def refresh(response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    """Called by the frontend when an access token expires, to get a new one
    without forcing the user to log in again."""
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    set_auth_cookies(response, create_access_token(user.id), create_refresh_token(user.id))
    return AuthResponse(message="Refreshed", user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


# ---- Google OAuth flow ----

@router.get("/login/google")
async def login_google(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Google login not configured on server")
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@router.get("/auth/google/callback")
async def auth_google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo") or await oauth.google.userinfo(token=token)
    except Exception:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=google_failed")

    email = (userinfo.get("email") or "").lower()
    google_id = userinfo.get("sub")
    username = userinfo.get("name") or (email.split("@")[0] if email else None)

    if not email:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=no_email")

    user = await _get_user_by_email(db, email)
    if user:
        if not user.google_id:
            user.google_id = google_id
            await db.commit()
    else:
        user = User(email=email, username=username, google_id=google_id, password_hash=None)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    redirect_resp = RedirectResponse(f"{settings.FRONTEND_URL}/dashboard")
    set_auth_cookies(redirect_resp, create_access_token(user.id), create_refresh_token(user.id))
    return redirect_resp
