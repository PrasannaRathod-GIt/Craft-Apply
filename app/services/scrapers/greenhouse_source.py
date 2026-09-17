"""
Greenhouse's Job Board API is public and keyless for GET requests:
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

Find a company's board_token from their careers page URL:
    https://boards.greenhouse.io/{board_token}
(e.g. https://boards.greenhouse.io/stripe -> token is "stripe")

This only covers companies that use Greenhouse as their ATS. Add a GREENHOUSE_BOARDS
config entry per company you want to track — there's no directory/search endpoint,
you have to know the token.
"""

import re
from typing import Dict, List

import httpx

from .schemas import RawJobListing

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


async def fetch_greenhouse_jobs(board_tokens: Dict[str, str]) -> List[RawJobListing]:
    """
    board_tokens: {"stripe": "Stripe", "figma": "Figma"} -- maps board token to the
    display name you want stored as `company`, since Greenhouse's list endpoint
    doesn't return a friendly company name itself.
    """
    listings: List[RawJobListing] = []

    async with httpx.AsyncClient(timeout=20) as client:
        for token, display_name in board_tokens.items():
            url = GREENHOUSE_API.format(token=token)
            try:
                resp = await client.get(url, params={"content": "true"})
                resp.raise_for_status()
            except httpx.HTTPError:
                # bad token or board temporarily down -- skip it, don't kill the whole run
                continue

            data = resp.json()
            for job in data.get("jobs", [])[:10]:  # cap per company to keep listings diverse across sources
                location = (job.get("location") or {}).get("name")
                content_html = job.get("content") or ""
                description = _strip_html(content_html)

                listings.append(
                    RawJobListing(
                        title=(job.get("title") or "").strip(),
                        company=display_name,
                        location=location,
                        short_desc=description[:280],
                        description=description,
                        apply_url=job.get("absolute_url"),
                        source="official",
                    )
                )

    return listings
