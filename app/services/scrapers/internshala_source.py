"""
Internshala's /jobs/ listing is server-rendered (confirmed live), so a plain GET +
BeautifulSoup works -- no headless browser needed. Pagination is /jobs/page-2/,
/jobs/page-3/, etc.

IMPORTANT CAVEATS, read before you turn this on in production:
1. This finds job cards by locating '<a href*="/job/detail/">' links rather than
   by CSS class name, so it survives most redesigns better than a class-based
   selector would -- but the company/location/salary extraction below is a text
   heuristic on the surrounding block, not a real structured parse. Run it once,
   dump the results, and eyeball 15-20 rows before trusting it in the daily cron.
2. Confirm this still fits Internshala's current Terms & Conditions before you
   schedule it to run automatically -- ToS pages change, and this is your call
   to make, not something I can verify for you here.
3. Politeness: this sleeps between page requests and sends a descriptive
   User-Agent. Don't remove either -- and don't crank `pages` up aggressively.
"""

import asyncio
import re
from typing import List

import httpx
from bs4 import BeautifulSoup

from .schemas import RawJobListing

BASE = "https://internshala.com"

HEADERS = {
    # Replace with your actual domain/contact -- identifying your bot honestly
    # is both more polite and easier to defend if anyone asks questions later.
    "User-Agent": "Mozilla/5.0 (compatible; YourAppJobBot/1.0; +https://yourdomain.com/about-bot)"
}

_SALARY_RE = re.compile(r"₹[\d,]+\s*-\s*[\d,]+\s*/year")
_EXPERIENCE_RE = re.compile(r"(\d+\+?\s*year\(s\)|No experience required|Fresher)", re.I)


async def fetch_internshala_jobs(pages: int = 1) -> List[RawJobListing]:
    listings: List[RawJobListing] = []

    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        for page in range(1, pages + 1):
            url = f"{BASE}/jobs/" if page == 1 else f"{BASE}/jobs/page-{page}/"
            resp = await client.get(url)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            for link in soup.select('a[href*="/job/detail/"]'):
                title = link.get_text(strip=True)
                href = link.get("href")
                if not title or not href:
                    continue
                apply_url = href if href.startswith("http") else BASE + href

                # Walk up a few parent levels to grab the surrounding card's text
                container = link
                for _ in range(4):
                    if container.parent is None:
                        break
                    container = container.parent
                block_text = container.get_text("\n", strip=True)
                lines = [l for l in block_text.split("\n") if l.strip()]

                salary_match = _SALARY_RE.search(block_text)
                exp_match = _EXPERIENCE_RE.search(block_text)

                listings.append(
                    RawJobListing(
                        title=title,
                        company=lines[1] if len(lines) > 1 else None,
                        location=lines[2] if len(lines) > 2 else None,
                        salary=salary_match.group(0) if salary_match else None,
                        job_type=exp_match.group(0) if exp_match else None,
                        short_desc=block_text[:280],
                        apply_url=apply_url,
                        source="internshala",
                    )
                )

            await asyncio.sleep(2)  # be polite between page requests

    return listings
