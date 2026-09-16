from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    eligibility: Optional[str] = None
    education: Optional[str] = None
    experience: Optional[str] = None
    short_desc: Optional[str] = None
    description: Optional[str] = None
    skills: Optional[str] = None
    salary: Optional[str] = None
    last_date: Optional[str] = None
    apply_url: str
    posted_date: Optional[date] = None
    is_active: bool = True


class JobCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: Optional[str] = None
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    short_desc: Optional[str] = None
    image_url: Optional[str] = None
    posted_date: Optional[date] = None


class JobDetailOut(JobCardOut):
    job_type: Optional[str] = None
    eligibility: Optional[str] = None
    education: Optional[str] = None
    experience: Optional[str] = None
    description: Optional[str] = None
    skills: Optional[str] = None
    salary: Optional[str] = None
    last_date: Optional[str] = None
    apply_url: str
    source: str


class JobListOut(BaseModel):
    jobs: List[JobCardOut]
    page: int
    total_pages: int
    total: int