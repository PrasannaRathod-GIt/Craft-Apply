from typing import Optional

from pydantic import BaseModel


class RawJobListing(BaseModel):
    """Common shape every scraper adapter normalizes into before it hits job_service."""
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    short_desc: Optional[str] = None
    description: Optional[str] = None
    salary: Optional[str] = None
    apply_url: str
    source: str  # 'official' | 'adzuna' | 'internshala'
