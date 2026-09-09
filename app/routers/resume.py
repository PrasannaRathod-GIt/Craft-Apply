from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user_optional
from app.models.submission import Submission
from app.models.user import User
from app.schemas.resume import (
    ResumeData,
    ResumeParseResponse,
    ResumeTailorRequest,
    ResumeTailorResponse,
)
from app.services.gemini import parse_resume_text, tailor_resume
from app.services.text_extraction import extract_text_from_upload

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/parse", response_model=ResumeParseResponse)
async def parse_resume(
    text: str | None = Form(default=None),
    file: Any = File(default=None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Accepts EITHER pasted text OR an uploaded PDF/DOCX (not both).
    Sign-in is optional here so users can try the builder before creating an account -
    the submission just won't be tied to a user_id until they sign up.

    Note on the 'file' param type: Swagger UI's "Try it out" sends an empty string
    for an unfilled optional file field instead of omitting it entirely, which breaks
    strict UploadFile typing. We accept Any here and normalize manually below."""
    if isinstance(file, str) or (file is not None and not getattr(file, "filename", None)):
        file = None  # normalize Swagger UI's empty-string quirk to a real None

    if not text and not file:
        raise HTTPException(400, "Provide either 'text' or 'file'.")
    if text and file:
        raise HTTPException(400, "Provide only one of 'text' or 'file', not both.")

    raw_text = text if text else await extract_text_from_upload(file)

    resume_data = await parse_resume_text(raw_text)

    submission = Submission(
        user_id=user.id if user else None,
        template="canonical",
        data=resume_data.model_dump(mode="json"),
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return ResumeParseResponse(submission_id=submission.id, data=resume_data)


@router.post("/tailor", response_model=ResumeTailorResponse)
async def tailor(
    payload: ResumeTailorRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Takes an existing submission + a job description, returns a NEW submission
    with re-weighted content. Never overwrites the original - full version history."""
    result = await db.execute(select(Submission).where(Submission.id == payload.submission_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(404, "Original submission not found")

    existing_data = ResumeData.model_validate(original.data)
    tailored_data, match_notes = await tailor_resume(existing_data, payload.job_description)

    new_submission = Submission(
        user_id=user.id if user else original.user_id,
        template=original.template,
        data=tailored_data.model_dump(mode="json"),
        parent_submission_id=original.id,
        job_description=payload.job_description,
    )
    db.add(new_submission)
    await db.commit()
    await db.refresh(new_submission)

    return ResumeTailorResponse(
        submission_id=new_submission.id,
        parent_submission_id=original.id,
        data=tailored_data,
        match_notes=match_notes,
    )


@router.get("/{submission_id}", response_model=ResumeData)
async def get_resume(submission_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(404, "Submission not found")
    return ResumeData.model_validate(submission.data)
