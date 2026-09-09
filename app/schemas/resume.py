"""The single canonical schema for a resume, used across every template.

Every existing template (template1-8) mapped raw form fields to ad-hoc dict keys
(experiences vs experience, about vs summary, etc). This schema replaces all of
that: Gemini always returns data shaped like this, every template's rendering
config maps FROM this shape TO its own field layout.
"""
from pydantic import BaseModel, Field


class ExperienceEntry(BaseModel):
    role: str = ""
    company: str = ""
    location: str | None = None
    start_date: str = ""
    end_date: str = ""  # "" or "Present"
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    degree: str = ""
    institution: str = ""
    year: str = ""
    details: str | None = None


class ProjectEntry(BaseModel):
    name: str = ""
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    link: str | None = None


class CertificateEntry(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str | None = None


class AchievementEntry(BaseModel):
    description: str = ""
    date: str | None = None


class ContactInfo(BaseModel):
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str | None = None
    website: str | None = None


class ResumeData(BaseModel):
    """The canonical shape. Gemini is prompted to return exactly this structure."""

    name: str = ""
    title: str = ""  # e.g. "Senior Backend Engineer"
    summary: str = ""  # aka "about"

    contact: ContactInfo = Field(default_factory=ContactInfo)

    experiences: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certificates: list[CertificateEntry] = Field(default_factory=list)
    achievements: list[AchievementEntry] = Field(default_factory=list)

    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    profile_photo_url: str | None = None

    model_config = {
        "json_schema_extra": {
            "description": "Canonical resume data structure - the single source of truth every template renders from."
        }
    }


class ResumeParseRequest(BaseModel):
    """Body for POST /resume/parse when submitting raw text (not a file)."""
    raw_text: str


class ResumeParseResponse(BaseModel):
    submission_id: int
    data: ResumeData


class ResumeTailorRequest(BaseModel):
    submission_id: int  # the existing resume to tailor
    job_description: str


class ResumeTailorResponse(BaseModel):
    submission_id: int  # NEW submission id (never overwrites the original)
    parent_submission_id: int
    data: ResumeData
    match_notes: str = ""  # brief explanation of what was re-weighted and why
