from typing import Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_utils import make_dedup_hash, make_slug
from app.models.job import Job
from app.schemas.job import JobCreate


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    counter = 2
    while True:
        result = await db.execute(select(Job.id).where(Job.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


async def create_job(
    db: AsyncSession,
    payload: JobCreate,
    image_url: Optional[str],
    source: str = "manual",
) -> Job:
    base_slug = make_slug(f"{payload.title}-{payload.company}") or make_slug(payload.title) or "job"
    slug = await _unique_slug(db, base_slug)
    dedup_hash = make_dedup_hash(payload.title, payload.company, payload.location)

    job = Job(
        title=payload.title,
        slug=slug,
        company=payload.company,
        location=payload.location,
        job_type=payload.job_type,
        eligibility=payload.eligibility,
        education=payload.education,
        experience=payload.experience,
        short_desc=payload.short_desc,
        description=payload.description,
        skills=payload.skills,
        salary=payload.salary,
        last_date=payload.last_date,
        apply_url=payload.apply_url,
        image_url=image_url,
        source=source,
        dedup_hash=dedup_hash,
        is_active=payload.is_active,
        **({"posted_date": payload.posted_date} if payload.posted_date else {}),
    )

    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("A job with this title, company, and location already exists.")

    await db.refresh(job)
    return job


async def list_active_jobs(
    db: AsyncSession, page: int = 1, per_page: int = 8
) -> Tuple[Sequence[Job], int, int]:
    offset = (page - 1) * per_page

    total = (
        await db.execute(select(func.count()).select_from(Job).where(Job.is_active.is_(True)))
    ).scalar_one()

    result = await db.execute(
        select(Job)
        .where(Job.is_active.is_(True))
        .order_by(Job.posted_date.desc(), Job.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    jobs = result.scalars().all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return jobs, total, total_pages


async def get_job_by_slug(db: AsyncSession, slug: str) -> Optional[Job]:
    result = await db.execute(select(Job).where(Job.slug == slug, Job.is_active.is_(True)))
    return result.scalar_one_or_none()


async def list_all_jobs_admin(
    db: AsyncSession, page: int = 1, per_page: int = 20
) -> Tuple[Sequence[Job], int]:
    offset = (page - 1) * per_page
    total = (await db.execute(select(func.count()).select_from(Job))).scalar_one()
    result = await db.execute(select(Job).order_by(Job.id.desc()).offset(offset).limit(per_page))
    return result.scalars().all(), total


async def set_job_active(db: AsyncSession, job_id: int, is_active: bool) -> Optional[Job]:
    job = await db.get(Job, job_id)
    if not job:
        return None
    job.is_active = is_active
    await db.commit()
    await db.refresh(job)
    return job