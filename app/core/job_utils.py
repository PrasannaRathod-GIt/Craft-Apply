"""
If you already have a make_slug() in app/core/utils.py from Phase 1, just
add make_dedup_hash() to that file instead of keeping this as a separate
module -- no need for two slug functions.
"""

import hashlib
import re
from typing import Optional


def make_slug(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def make_dedup_hash(title: str, company: Optional[str], location: Optional[str]) -> str:
    """
    Uses (title, company, location) rather than apply_url -- aggregator APIs
    like Adzuna return a rotating tracking URL per request, so hashing on
    apply_url meant the same real listing never matched itself twice.
    location is used instead of dropping the third field entirely, because
    title+company alone would wrongly collapse two real postings at the same
    company with the same title but different locations (e.g. "Software
    Engineer" in Bangalore vs. Hyderabad) into a single row.
    """
    key = f"{(title or '').strip().lower()}|{(company or '').strip().lower()}|{(location or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()