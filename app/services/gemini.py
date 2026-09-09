"""Single module for all Gemini calls. Two jobs:
1. Turn raw resume text into a structured ResumeData object (parse).
2. Take an existing ResumeData + a job description and re-weight it for ATS match (tailor).

Both use Gemini's JSON mode constrained to the ResumeData schema, so we always get
parseable structured output - never free text we have to regex out.
"""
import json

import google.generativeai as genai

from app.core.config import settings
from app.schemas.resume import ResumeData

_configured = False


def _ensure_configured() -> None:
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set - cannot call Gemini.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


_PARSE_SYSTEM_PROMPT = """You are a resume-parsing engine. Extract the resume text
into the exact JSON schema provided. Rules:
- Never invent information that isn't present in the source text.
- If a field isn't present, use an empty string or empty list - do not guess.
- Preserve bullet points as separate list items, don't merge them into one paragraph.
- Dates: keep the format used in the source (e.g. "Jan 2022", "2022", "06/2022").
- Skills: split on commas/bullets into a flat list of individual skill strings.
"""

_TAILOR_SYSTEM_PROMPT = """You are a resume-tailoring engine for ATS optimization.
Given an existing resume (as JSON) and a target job description, re-weight and
rephrase the resume to better match the job description's keywords and priorities.
Rules:
- Never invent experience, employers, dates, or credentials that aren't in the original.
- You MAY rephrase bullet points to surface relevant keywords from the job description,
  reorder skills to put the most relevant first, and tighten the summary to align with
  the role - but the underlying facts must stay true to the original.
- Return the full resume in the same JSON schema, plus a short match_notes string
  (1-3 sentences) explaining what you changed and why.
"""


def _resume_data_json_schema() -> dict:
    """Gemini's response_schema wants OpenAPI-style JSON schema, not Pydantic's dialect."""
    schema = ResumeData.model_json_schema()
    return _to_gemini_schema(schema)


def _to_gemini_schema(schema: dict) -> dict:
    """Strip fields Gemini's schema validator doesn't accept (Pydantic emits $defs,
    additionalProperties, title, etc. that need cleaning for the Gemini API)."""
    if "$defs" in schema:
        defs = schema.pop("$defs")
        schema = _inline_refs(schema, defs)
    schema.pop("title", None)
    schema.pop("description", None)
    return _clean(schema)


def _inline_refs(node, defs):
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            return _inline_refs(defs[ref_name], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


_SCHEMA_KEYWORDS = {"type", "properties", "items", "required", "format", "enum", "description"}


def _clean(node):
    """JSON-schema-aware cleanup. Must NOT blindly strip a 'title' key from every dict -
    ResumeData has an actual field named 'title' (job title), and if we treat every dict's
    'title' key as schema metadata we'd delete that field's own schema entry by mistake.
    So: only recurse as schema-keyword-aware, and treat 'properties' dict values (whose KEYS
    are field names, some of which happen to be 'title') differently from schema nodes."""
    if isinstance(node, list):
        return [_clean(v) for v in node]
    if not isinstance(node, dict):
        return node

    # Simplify Optional[str] (anyOf: [{type: string}, {type: null}]) down to plain string.
    if "anyOf" in node:
        non_null = [o for o in node["anyOf"] if o.get("type") != "null"]
        if non_null:
            merged = {k: v for k, v in node.items() if k != "anyOf"}
            merged.update(non_null[0])
            node = merged

    result: dict = {}
    for key, value in node.items():
        if key in ("title", "default", "anyOf"):
            continue  # strip JSON-schema metadata keywords, not field names
        if key == "properties" and isinstance(value, dict):
            # keys here are FIELD NAMES (e.g. "title" meaning job title) - keep them as-is,
            # only clean each field's own schema definition
            result[key] = {field_name: _clean(field_schema) for field_name, field_schema in value.items()}
        elif key in _SCHEMA_KEYWORDS or isinstance(value, (dict, list)):
            result[key] = _clean(value)
        else:
            result[key] = value
    return result


async def parse_resume_text(raw_text: str) -> ResumeData:
    _ensure_configured()
    model = genai.GenerativeModel(
        "gemini-3.6-flash",
        system_instruction=_PARSE_SYSTEM_PROMPT,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": _resume_data_json_schema(),
        },
    )
    response = await model.generate_content_async(raw_text)
    return ResumeData.model_validate(json.loads(response.text))


async def tailor_resume(existing: ResumeData, job_description: str) -> tuple[ResumeData, str]:
    _ensure_configured()

    tailor_response_schema = {
        "type": "object",
        "properties": {
            "resume": _resume_data_json_schema(),
            "match_notes": {"type": "string"},
        },
        "required": ["resume", "match_notes"],
    }

    model = genai.GenerativeModel(
        "gemini-3.6-flash",
        system_instruction=_TAILOR_SYSTEM_PROMPT,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": tailor_response_schema,
        },
    )
    prompt = (
        f"EXISTING RESUME (JSON):\n{existing.model_dump_json(indent=2)}\n\n"
        f"TARGET JOB DESCRIPTION:\n{job_description}"
    )
    response = await model.generate_content_async(prompt)
    parsed = json.loads(response.text)
    return ResumeData.model_validate(parsed["resume"]), parsed.get("match_notes", "")
