import cloudinary
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.routers import admin_jobs, auth, internal, jobs, resume
from app.services.gemini import GeminiRateLimitError

app = FastAPI(title="Resume Builder API")


@app.exception_handler(GeminiRateLimitError)
async def gemini_rate_limit_handler(request, exc):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


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
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(admin_jobs.router)
app.include_router(internal.router)


@app.get("/health")
async def health():
    return {"status": "ok"}