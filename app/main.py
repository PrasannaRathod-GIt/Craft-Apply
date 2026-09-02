import cloudinary
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.routers import auth

app = FastAPI(title="Resume Builder API")

# Session middleware is required by Authlib to store the OAuth `state` during the
# Google redirect round-trip. This is separate from your JWT auth cookies.
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,  # required so the browser sends/receives cookies cross-origin
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )

app.include_router(auth.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
