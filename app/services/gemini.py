"""Single module for all Gemini calls. Two jobs:
1. Turn raw resume text into a structured ResumeData object (parse).
2. Take an existing ResumeData + a job description and re-weight it for ATS match (tailor).

Uses the current Interactions API (`google-genai`, `client.aio.interactions.create`).

Calls per full run (parse + tailor): normally 3. The free tier allows only 20 requests/day
per model, so every call is spent deliberately. Flash-tier drops fields on big schemas,
so each call keeps its schema small, and a caller may pass `model` to pick which Gemini
model handles the request (frontend model selector).
"""
import re
from typing import Callable, TypeVar

from google import genai
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.resume import (
    AchievementEntry,
    CertificateEntry,
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    ResumeData,
)

MODEL = "gemini-3.5-flash-lite"  # backend default; callers may override via `model` param

_client: genai.Client | None = None

T = TypeVar("T", bound=BaseModel)


class GeminiRateLimitError(Exception):
    """Raised when Gemini returns 429 (quota exhausted). Turned into a clean HTTP 429 in main.py."""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set - cannot call Gemini.")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class _ParsedIdentity(BaseModel):
    name: str = Field(default="", description="The person's full name only. Nothing else.")
    title: str = Field(
        default="",
        description="Professional job title ONLY, 2-6 words, e.g. 'Software Engineer'. Copy it from the resume. Never invent one.",
    )
    summary: str = Field(default="", description="The summary/about paragraph exactly as written in the resume (2-4 sentences).")
    contact: ContactInfo = Field(default_factory=ContactInfo)
    languages: list[str] = Field(default_factory=list, description="Spoken languages only (e.g. English, Hindi). Empty if none listed.")


class _ParsedSkills(BaseModel):
    skills: list[str] = Field(
        default_factory=list,
        description="Only the items listed in the resume's dedicated skills section, one per list item.",
    )


class _ParsedSections(BaseModel):
    experiences: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certificates: list[CertificateEntry] = Field(default_factory=list)
    achievements: list[AchievementEntry] = Field(default_factory=list)


class _TailorPatch(BaseModel):
    """A small delta for tailoring - NOT the full resume (see tailor_resume)."""

    summary: str = Field(description="Rewritten 2-4 sentence professional summary aligned to the job description.")
    skills: list[str] = Field(description="The SAME skills from the original resume, reordered with most relevant first. Do not add or remove skills.")
    experience_order: list[int] = Field(
        description="0-based indices into the original experiences list, reordered with most relevant first. Must include every index from the original exactly once."
    )
    tailored_bullets: list[list[str]] = Field(
        description=(
            "One list of bullets per experience, in the ORIGINAL experience order (index 0 first, "
            "regardless of experience_order above). Rephrase each experience's existing bullets to "
            "emphasize job description keywords - do not add or remove bullets, only reword them."
        )
    )
    match_notes: str = Field(
        description="1-2 plain sentences, honestly describing what you changed (summary rewritten, skills and experiences reordered, bullets reworded) and why it helps match the job."
    )


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
_IDENTITY_PROMPT = """From the resume text below, extract ONLY: the person's name, their job title,
their summary paragraph, contact details (email, phone, location, linkedin, website), and any
spoken languages. Copy values from the text. Never invent anything - use an empty string or
empty list for anything missing.

RESUME TEXT:
"""

_SKILLS_PROMPT = """From the resume text below, extract ONLY the items written in the resume's dedicated
skills section (one list item per skill). Do NOT infer skills from experience bullets, projects or
summaries. If there is no dedicated skills section, return an empty list.

RESUME TEXT:
"""

_SECTIONS_PROMPT = """From the resume text below, extract ONLY: work experience, education, projects,
certificates and achievements. For each experience keep every bullet point as its own list item.
Never invent anything - use an empty list for sections that are missing.

RESUME TEXT:
"""

_TAILOR_INSTRUCTIONS = """Given this resume's summary, skills, and work experience, produce
a small tailoring patch (NOT the full resume) to better match the job description.

RESUME SUMMARY: {summary}
RESUME SKILLS: {skills}
RESUME EXPERIENCES (0-indexed, each with its existing bullets):
{experiences_text}

JOB DESCRIPTION:
{job_description}

Return: a rewritten summary, the same skills reordered by relevance, the experience
indices reordered by relevance, rephrased bullets for each experience (same order
as given above, index 0 first, same number of bullets, just reworded), and brief match notes.

STRICT HONESTY RULES:
- Use only facts already stated in the resume above. Never add a tool, technology, employer,
  metric or responsibility that is not stated.
- Never add a technology to a bullet unless that exact bullet already mentions it.
- Keep every number exactly as written.
- Do not claim seniority, years of experience or titles the resume does not state
  (no "Senior", "Lead" or "Architect" unless the resume says so).
- Do not mention job requirements the resume does not support.
- Mirror the job description's wording only where the resume already supports it.
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _generate(
    model_cls: type[T],
    prompt: str,
    is_empty: Callable[[T], bool] | None = None,
    attempts: int = 2,
    model: str = MODEL,
) -> T:
    """One schema-constrained Gemini call, retried only if the result looks empty."""
    client = _get_client()
    result: T | None = None
    for _ in range(attempts):
        try:
            interaction = await client.aio.interactions.create(
                model=model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": model_cls.model_json_schema(),
                },
            )
        except Exception as e:
            if type(e).__name__ == "RateLimitError" or "429" in str(e):
                raise GeminiRateLimitError(
                    "The AI service has hit its daily free-tier limit. Please try again later."
                ) from e
            raise
        result = model_cls.model_validate_json(interaction.output_text)
        if is_empty is None or not is_empty(result):
            return result
    assert result is not None
    return result


def _skills_from_text(raw_text: str) -> list[str]:
    """Plain-text extraction of a 'Skills: a, b, c' line straight from the resume."""
    m = re.search(r"(?im)^\s*(?:technical\s+|key\s+|core\s+)?skills?\s*[:\-]\s*(.+)$", raw_text)
    if not m:
        return []
    parts = re.split(r"[,;|\u2022]", m.group(1))
    return [p.strip(" .\t") for p in parts if p.strip(" .\t")]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _clean_title(title: str, raw_text: str, name: str) -> str:
    """A job title is a short phrase. If the model returned something long, fall back to
    the first short non-name line near the top of the resume."""
    title = (title or "").strip()
    if 0 < len(title.split()) <= 6:
        return title
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    for ln in lines[:4]:
        if ln.lower() != (name or "").strip().lower() and 0 < len(ln.split()) <= 6 and "@" not in ln:
            return ln
    return ""


def _contact_from_text(raw_text: str) -> ContactInfo:
    """Plain-text fallback: pull an email and phone number straight from the resume
    if the identity call returned them empty."""
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw_text)
    phone_match = re.search(r"(?:\+?\d[\d\-\s]{7,}\d)", raw_text)
    return ContactInfo(
        email=email_match.group(0) if email_match else "",
        phone=phone_match.group(0).strip() if phone_match else "",
    )


# --------------------------------------------------------------------------- #
# Parse
# --------------------------------------------------------------------------- #
async def parse_resume_text(raw_text: str, model: str | None = None) -> ResumeData:
    selected_model = model or MODEL

    identity = await _generate(
        _ParsedIdentity,
        _IDENTITY_PROMPT + raw_text,
        is_empty=lambda r: not r.name or not (r.contact.email or r.contact.phone),
        model=selected_model,
    )
    contact = identity.contact
    if not contact.email and not contact.phone:
        contact = _contact_from_text(raw_text)

    sections = await _generate(
        _ParsedSections,
        _SECTIONS_PROMPT + raw_text,
        is_empty=lambda r: not r.experiences and not r.education,
        model=selected_model,
    )

    # An explicit "Skills:" line wins and costs zero API calls.
    skill_list = _dedupe(_skills_from_text(raw_text))
    if not skill_list:
        skills = await _generate(_ParsedSkills, _SKILLS_PROMPT + raw_text, attempts=1, model=selected_model)
        skill_list = _dedupe(skills.skills)

    return ResumeData(
        name=identity.name,
        title=_clean_title(identity.title, raw_text, identity.name),
        summary=identity.summary,
        contact=contact,
        skills=skill_list,
        languages=identity.languages,
        experiences=sections.experiences,
        education=sections.education,
        projects=sections.projects,
        certificates=sections.certificates,
        achievements=sections.achievements,
    )


# --------------------------------------------------------------------------- #
# Tailor
# --------------------------------------------------------------------------- #
async def tailor_resume(
    existing: ResumeData, job_description: str, model: str | None = None
) -> tuple[ResumeData, str]:
    selected_model = model or MODEL

    experiences_text = "\n".join(
        f"[{i}] {exp.role} at {exp.company}:\n" + "\n".join(f"  - {b}" for b in exp.bullets)
        for i, exp in enumerate(existing.experiences)
    ) or "(no experiences listed)"

    prompt = _TAILOR_INSTRUCTIONS.format(
        summary=existing.summary or "(none)",
        skills=", ".join(existing.skills) if existing.skills else "(none)",
        experiences_text=experiences_text,
        job_description=job_description,
    )
    patch = await _generate(_TailorPatch, prompt, attempts=1, model=selected_model)

    # Merge the patch into a COPY of the original - fields the model never sees
    # (name, title, contact, education, projects, ...) are guaranteed unchanged.
    tailored = existing.model_copy(deep=True)
    tailored.summary = patch.summary or existing.summary

    original_skills = set(existing.skills)
    patched_skills = [s for s in patch.skills if s in original_skills]
    # Safety net: if the model dropped or invented a skill, keep the original list.
    tailored.skills = patched_skills if set(patched_skills) == original_skills else existing.skills

    if len(patch.tailored_bullets) == len(existing.experiences) and sorted(patch.experience_order) == list(
        range(len(existing.experiences))
    ):
        reordered = []
        for idx in patch.experience_order:
            exp = existing.experiences[idx].model_copy(deep=True)
            new_bullets = patch.tailored_bullets[idx]
            # Only accept rephrased bullets if the count matches the original.
            if len(new_bullets) == len(exp.bullets):
                exp.bullets = new_bullets
            reordered.append(exp)
        tailored.experiences = reordered

    return tailored, (patch.match_notes or "").strip()