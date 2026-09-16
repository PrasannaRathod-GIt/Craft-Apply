from datetime import date
from typing import Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_guard import require_admin
from app.core.database import get_db
from app.schemas.job import JobCardOut, JobCreate
from app.services import job_service
from app.services.cloudinary_service import upload_job_image

router = APIRouter(prefix="/admin/jobs", tags=["admin-jobs"])


@router.post("", response_model=JobCardOut, dependencies=[Depends(require_admin)])
async def add_job(
    title: str = Form(...),
    company: str = Form(""),
    location: str = Form(""),
    job_type: str = Form(""),
    eligibility: str = Form(""),
    education: str = Form(""),
    experience: str = Form(""),
    short_desc: str = Form(""),
    description: str = Form(""),
    skills: str = Form(""),
    salary: str = Form(""),
    last_date: str = Form(""),
    apply_url: str = Form(...),
    posted_date: Optional[date] = Form(None),
    is_active: bool = Form(True),
    # Accepts UploadFile OR str because some multipart clients (Swagger UI's
    # "Try it out" included) send an empty string instead of omitting the
    # field entirely when no file is picked -- we normalize that below.
    image_file: Union[UploadFile, str, None] = File(default=None),
    db: AsyncSession = Depends(get_db),
):
    payload = JobCreate(
        title=title,
        company=company or None,
        location=location or None,
        job_type=job_type or None,
        eligibility=eligibility or None,
        education=education or None,
        experience=experience or None,
        short_desc=short_desc or None,
        description=description or None,
        skills=skills or None,
        salary=salary or None,
        last_date=last_date or None,
        apply_url=apply_url,
        posted_date=posted_date,
        is_active=is_active,
    )

    # Normalize: treat "no real file" (empty string, or an UploadFile with no
    # filename) as None so upload_job_image never sees a non-file value.
    real_file = image_file if isinstance(image_file, UploadFile) and image_file.filename else None
    image_url = await upload_job_image(real_file)

    try:
        job = await job_service.create_job(db, payload, image_url, source="manual")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return job


@router.patch("/{job_id}/active", dependencies=[Depends(require_admin)])
async def toggle_job_active(job_id: int, is_active: bool, db: AsyncSession = Depends(get_db)):
    job = await job_service.set_job_active(db, job_id, is_active)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "id": job.id, "is_active": job.is_active}