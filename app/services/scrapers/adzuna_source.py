"""
Adzuna (developer.adzuna.com) has a genuinely free, keyed API -- register for an
app_id/app_key pair, roughly 1,000 calls/month on the free tier. It's an
aggregator (pulls from Indeed and other boards depending on country), so store
the source as 'adzuna' rather than mislabeling it 'indeed' -- it's honest about
where the data actually came from, and `redirect_url` still points at the real
original listing, which is what matters for your thumbnail-then-redirect flow.
"""

from typing import List, Optional

import httpx

from .schemas import RawJobListing

ADZUNA_API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _format_salary(job: dict) -> Optional[str]:
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo and hi:
        return f"{lo:,.0f} - {hi:,.0f}"
    return None


async def fetch_adzuna_jobs(
    app_id: str,
    app_key: str,
    country: str = "in",
    query: str = "",
    pages: int = 1,
    results_per_page: int = 20,
) -> List[RawJobListing]:
    listings: List[RawJobListing] = []

    async with httpx.AsyncClient(timeout=20) as client:
        for page in range(1, pages + 1):
            url = ADZUNA_API.format(country=country, page=page)
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": results_per_page,
                "what": query,
                "content-type": "application/json",
            }
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                break

            results = resp.json().get("results", [])
            if not results:
                break

            for job in results:
                listings.append(
                    RawJobListing(
                        title=(job.get("title") or "").strip(),
                        company=(job.get("company") or {}).get("display_name"),
                        location=(job.get("location") or {}).get("display_name"),
                        short_desc=(job.get("description") or "")[:280],
                        description=job.get("description"),
                        salary=_format_salary(job),
                        apply_url=job.get("redirect_url"),
                        source="adzuna",
                    )
                )

    return listings
