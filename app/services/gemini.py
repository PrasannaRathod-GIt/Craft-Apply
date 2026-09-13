"""Single module for all Gemini calls. Two jobs:
1. Turn raw resume text into a structured ResumeData object (parse).
2. Take an existing ResumeData + a job description and re-weight it for ATS match (tailor).

IMPORTANT - uses the current Interactions API (`google-genai` package, `client.interactions.create`),
NOT the older `google.generativeai` package's `GenerativeModel.generate_content`. That older package
is now legacy and does not correctly enforce response_format/schema against current model versions -
confirmed via testing: it silently let the model dump free text into the first schema field instead
of respecting the schema. The current API also accepts Pydantic's `model_json_schema()` output
directly with no manual cleanup needed - the manual schema-surgery code that used to live in this
file was solving a problem that doesn't exist with this API and has been removed entirely.
"""
import json

from google import genai
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.resume import ResumeData

MODEL = "gemini-3.6-flash"  # free tier gives ZERO quota for pro-tier models (confirmed
# via a 429 "limit: 0" error) - flash is what's actually available. The fix for its
# unreliability on the full-object tailor task isn't a bigger model, it's a smaller task:
# see TailorPatch below - we stopped asking it to reproduce data it doesn't need to touch.

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set - cannot call Gemini.")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


class _TailorPatch(BaseModel):
    """A small delta the model needs to produce for tailoring - NOT the full resume.
    Asking flash-tier to reproduce the entire ResumeData object (10+ fields, nested
    arrays) repeatedly caused degenerate repetition loops. Asking for only this small
    patch, then merging it into the original in Python (see tailor_resume below),
    eliminates the failure mode entirely: the model never has to touch fields it
    doesn't need to change, so there's nothing for it to corrupt or drop."""

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


_PARSE_INSTRUCTIONS = """Extract the resume text below into the JSON schema provided.
Never invent information not present in the source text - use empty string/list for
missing fields. Preserve bullet points as separate list items.

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
indices reordered by relevance, and rephrased bullets for each experience (same order
as given above, index 0 first) - same number of bullets per experience, just reworded
to emphasize job description keywords. Do not invent new skills, employers, or bullets.
"""

_MATCH_NOTES_PROMPT = """A resume was tailored for this job description:
{job_description}

The tailored resume now emphasizes:
- Title: {title}
- Summary: {summary}
- Top skills: {skills}

In 1-2 short plain sentences, explain what was changed and why it helps match this job.
Do not repeat the full resume content - just a brief explanation. Plain text, no JSON."""


async def parse_resume_text(raw_text: str) -> ResumeData:
    client = _get_client()
    interaction = await client.aio.interactions.create(
        model=PARSE_MODEL,
        input=_PARSE_INSTRUCTIONS + raw_text,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": ResumeData.model_json_schema(),
        },
    )
    return ResumeData.model_validate_json(interaction.output_text)


async def tailor_resume(existing: ResumeData, job_description: str) -> tuple[ResumeData, str]:
    client = _get_client()

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
    interaction = await client.aio.interactions.create(
        model=MODEL,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": _TailorPatch.model_json_schema(),
        },
    )
    patch = _TailorPatch.model_validate_json(interaction.output_text)

    # Merge the patch into a COPY of the original - every field neither the model nor
    # this function touches (name, title, contact, education, projects, certificates,
    # achievements, languages, profile_photo_url) is guaranteed identical to the input,
    # because we never asked the model to reproduce it in the first place.
    tailored = existing.model_copy(deep=True)
    tailored.summary = patch.summary

    original_skills = set(existing.skills)
    patched_skills = [s for s in patch.skills if s in original_skills]
    # Safety net: if the model dropped or invented a skill despite instructions,
    # fall back to the original list rather than silently losing data.
    tailored.skills = patched_skills if set(patched_skills) == original_skills else existing.skills

    if len(patch.tailored_bullets) == len(existing.experiences) and sorted(patch.experience_order) == list(
        range(len(existing.experiences))
    ):
        reordered = []
        for idx in patch.experience_order:
            exp = existing.experiences[idx].model_copy(deep=True)
            new_bullets = patch.tailored_bullets[idx]
            # Per-experience safety net: only accept rephrased bullets if the count
            # matches the original - a mismatched count means the model dropped or
            # invented bullets for this specific experience, so fall back to its
            # original bullets rather than risk losing or fabricating content.
            if len(new_bullets) == len(exp.bullets):
                exp.bullets = new_bullets
            reordered.append(exp)
        tailored.experiences = reordered
    # else: model's indices/lengths didn't line up at all - leave experiences as the
    # original, untouched copy rather than risk corrupting them.

    # Separate, schema-free call for the human-readable explanation.
    notes_prompt = _MATCH_NOTES_PROMPT.format(
        job_description=job_description,
        title=tailored.title or "(unchanged)",
        summary=tailored.summary or "(unchanged)",
        skills=", ".join(tailored.skills[:5]) if tailored.skills else "(none)",
    )
    notes_interaction = await client.aio.interactions.create(model=MODEL, input=notes_prompt)
    match_notes = (notes_interaction.output_text or "").strip()

    return tailored, match_notes
