"""
Protected by a shared secret header, not user JWT -- this is meant to be called
by a Render Cron Job (or any server-to-server caller), not a logged-in browser.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.scraper_service import run_daily_scrape

router = APIRouter(prefix="/internal", tags=["internal"])


async def verify_internal_secret(x_internal_secret: str = Header(...)):
    if x_internal_secret != settings.INTERNAL_SCRAPE_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal secret")


@router.post("/scrape", dependencies=[Depends(verify_internal_secret)])
async def trigger_scrape(db: AsyncSession = Depends(get_db)):
    summary = await run_daily_scrape(db)
    return {
        "ok": True,
        "created": summary.created,
        "skipped_duplicate": summary.skipped_duplicate,
        "errored": summary.errored,
        "by_source": summary.by_source,
    }
