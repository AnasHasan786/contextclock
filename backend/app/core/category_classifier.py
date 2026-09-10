"""
LLM-based memory category classification.

Assigns a MemoryCategory to a memory (or a related old/new memory
pair) based on its content. Follows the same structural pattern as
contradiction.py: Gemini call, Pydantic response_schema enforcement,
safe fallback on any failure.

Primary use case: assigning MemoryCategory to STALE dataset records,
which arrive as raw (m_old, m_new) text pairs with no category field
of their own. Only ~12% of STALE explanations carry an extractable
ontology-style tag (verified empirically -- see
app/evaluation/build_stale_dataset.py), so this classifier is the
primary category-assignment mechanism, not a fallback.

Design choice: m_old and m_new are classified JOINTLY in a single
call, producing one shared category, rather than classified
independently. Rationale: by construction, m_old and m_new describe
competing claims about the SAME underlying fact (that's what makes
them a valid STALE conflict pair), so they must share a category.
Joint classification is both cheaper (400 calls instead of 800 for
the full STALE set) and structurally guarantees this consistency,
rather than hoping two independent classifications happen to agree.

This module also supports classifying a single piece of content with
no counterpart (related_content=None), for future production use
where a new memory is stored without an explicit category.
"""

import os
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.models.memory import MemoryCategory

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-3.6-flash"

# Safe fallback category on any classification failure. FACT is
# ContextClock's generic catch-all category (730-day half-life,
# "general facts decay slowly" per decay.py) -- a defensible neutral
# default that avoids over- or under-estimating staleness relative
# to a wrong specific-category guess.
FALLBACK_CATEGORY = MemoryCategory.FACT


class CategoryClassificationResult(BaseModel):
    """
    Structured output schema enforced on Gemini's response via
    response_schema, matching the pattern used in contradiction.py.
    """
    category: MemoryCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


_TASK_INSTRUCTIONS = f"""
You are categorizing a memory (or a pair of related memories) stored
by an AI agent about a user, to determine which category best
describes what kind of fact it represents. This category determines
how quickly the memory is expected to become stale over time.

Choose exactly one of the following categories:

- {MemoryCategory.EMPLOYMENT.value}: job, employer, role, work status,
  income source, or professional situation.
- {MemoryCategory.LOCATION.value}: where the user lives, works from,
  or is physically based -- city, region, timezone, commute, or
  housing situation.
- {MemoryCategory.RELATIONSHIP.value}: family, friendships, romantic
  relationships, social circle, or social network structure.
- {MemoryCategory.PREFERENCE.value}: likes, dislikes, habits,
  routines, or recurring behavioral patterns that could plausibly
  shift over time (e.g. exercise routine, diet, hobbies).
- {MemoryCategory.PERSONAL.value}: near-permanent personal
  attributes -- name, birthday, nationality, or other facts that
  almost never change.
- {MemoryCategory.FACT.value}: general factual statements that don't
  clearly fit the categories above.

If given two related memories (an older and a newer one describing
the same evolving fact), assign ONE category that applies to both --
they describe the same underlying fact, just at different points in
time, so they must share a category.

Provide a confidence score between 0.0 and 1.0, and a short,
one-sentence reasoning for your choice.
"""


def _fallback_result(error_context: str) -> CategoryClassificationResult:
    return CategoryClassificationResult(
        category=FALLBACK_CATEGORY,
        confidence=0.0,
        reasoning=error_context,
    )


def classify_memory_category(
    content: str,
    related_content: Optional[str] = None,
    model: str = MODEL_NAME,
) -> CategoryClassificationResult:
    """
    Classifies the MemoryCategory of `content`, optionally alongside
    `related_content` (e.g. an old/new memory pair from STALE) so a
    single shared category is assigned to both.

    model: overrides which Gemini model is called. Defaults to
    MODEL_NAME (gemini-3.6-flash), matching production behavior.
    Evaluation code may pass a different model -- e.g.
    gemini-3.5-flash-lite -- to work around gemini-3.6-flash's
    restrictive free-tier daily quota (20 requests/day, confirmed
    from a live 429 response) when running large batch evaluations.
    This is a disclosed evaluation-only deviation from the production
    default, not a silent inconsistency -- see
    app/evaluation/build_stale_dataset.py for where it's applied.

    Does NOT raise on failure -- any error (network, rate limit,
    malformed response, safety filter block) returns a safe fallback:
    category=FACT, confidence=0.0, with the error recorded in
    `reasoning`. This mirrors detect_contradiction()'s fallback
    philosophy in contradiction.py: callers always get a usable
    result, never an exception to handle.
    """
    if related_content is not None:
        prompt = (
            _TASK_INSTRUCTIONS
            + "\n\nOlder memory:\n"
            + f"  {content}\n"
            + "\nNewer memory:\n"
            + f"  {related_content}\n"
        )
    else:
        prompt = _TASK_INSTRUCTIONS + f"\n\nMemory:\n  {content}\n"

    try:
        response = _client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CategoryClassificationResult,
            ),
        )
    except Exception as e:
        return _fallback_result(f"API call failed: {type(e).__name__}: {e}")

    if response.parsed is None:
        raw_text = getattr(response, "text", None)
        return _fallback_result(f"Response did not parse to schema. Raw: {raw_text!r}")

    return response.parsed