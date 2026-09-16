from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings  # add the new fields listed in the setup notes
from app.schemas.job import JobCreate
from app.services import job_service
from app.services.scrapers.adzuna_source import fetch_adzuna_jobs
from app.services.scrapers.greenhouse_source import fetch_greenhouse_jobs
from app.services.scrapers.internshala_source import fetch_internshala_jobs
from app.services.scrapers.schemas import RawJobListing


@dataclass
class ScrapeSummary:
    created: int = 0
    skipped_duplicate: int = 0
    errored: int = 0
    by_source: Dict[str, int] = field(default_factory=dict)


def _raw_to_job_create(raw: RawJobListing) -> JobCreate:
    return JobCreate(
        title=raw.title,
        company=raw.company,
        location=raw.location,
        job_type=raw.job_type,
        short_desc=raw.short_desc or (raw.description or "")[:280],
        description=raw.description,
        salary=raw.salary,
        apply_url=raw.apply_url,
        is_active=True,
    )


async def run_daily_scrape(db: AsyncSession) -> ScrapeSummary:
    summary = ScrapeSummary()
    all_raw: List[RawJobListing] = []

    if settings.GREENHOUSE_BOARDS:
        all_raw += await fetch_greenhouse_jobs(settings.GREENHOUSE_BOARDS)

    if settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY:
        all_raw += await fetch_adzuna_jobs(
            app_id=settings.ADZUNA_APP_ID,
            app_key=settings.ADZUNA_APP_KEY,
            country=settings.ADZUNA_COUNTRY,
            query=settings.ADZUNA_QUERY,
            pages=settings.ADZUNA_PAGES,
        )

    if settings.ENABLE_INTERNSHALA_SCRAPE:
        all_raw += await fetch_internshala_jobs(pages=settings.INTERNSHALA_PAGES)

    for raw in all_raw:
        summary.by_source[raw.source] = summary.by_source.get(raw.source, 0) + 1

        if not raw.title or not raw.apply_url:
            summary.errored += 1
            continue

        payload = _raw_to_job_create(raw)
        try:
            await job_service.create_job(db, payload, image_url=None, source=raw.source)
            summary.created += 1
        except ValueError:
            summary.skipped_duplicate += 1
        except Exception:
            summary.errored += 1

    return summary
