from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db  # adjust if your dependency lives elsewhere
from app.schemas.job import JobDetailOut, JobListOut
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListOut)
async def list_jobs(
    page: int = Query(1, ge=1),
    q: Optional[str] = Query(None, description="Keyword search across title, company, description"),
    job_type: Optional[str] = Query(None, description="e.g. remote, full-time, part-time, internship"),
    location: Optional[str] = Query(None, description="City name, or 'Anywhere' for no filter"),
    db: AsyncSession = Depends(get_db),
):
    jobs, total, total_pages = await job_service.list_active_jobs(
        db, page=page, q=q, job_type=job_type, location=location
    )
    return {"jobs": jobs, "page": page, "total_pages": total_pages, "total": total}


@router.get("/{slug}", response_model=JobDetailOut)
async def job_detail(slug: str, db: AsyncSession = Depends(get_db)):
    job = await job_service.get_job_by_slug(db, slug)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job