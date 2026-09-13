"""
LLM-based contradiction detection (Phase 2, Step 5).

Given exactly one (old_memory, new_memory) pair -- already selected
by the deterministic retrieval step in retrieval.py -- ask Gemini to
classify their semantic relationship using the schema locked in
during Phase 2 design:

    relationship: CONTRADICTS | SUPERSEDES | UNRELATED | CONSISTENT
    score:        0.0-1.0
    reasoning:    short explanation

IMPORTANT SCOPE NOTE: this module only makes the LLM call and returns
a validated result. Error handling / safe fallback on malformed or
failed responses is Step 6, deliberately kept separate so each piece
can be tested in isolation.
"""

import os
from enum import Enum
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.models.memory import Memory

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-3.6-flash"


class MemoryRelationship(str, Enum):
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    UNRELATED = "UNRELATED"
    CONSISTENT = "CONSISTENT"


class ContradictionResult(BaseModel):
    """
    Structured output schema enforced on Gemini's response via
    response_schema. Gemini cannot return anything that doesn't
    validate against this shape.
    """
    relationship: MemoryRelationship
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


# The task description Gemini receives. Deliberately does NOT
# include example JSON output -- the response_schema mechanism
# already enforces format, and Google's own docs note that
# duplicating schema/examples in the prompt reduces output quality.
_TASK_INSTRUCTIONS = """
You are comparing two memories stored by an AI agent about the same
user, to determine how the newer memory relates to the older one.

Classify the relationship as exactly one of:

- CONTRADICTS: the two memories claim incompatible things about the
  present state, and the newer memory does NOT explicitly name or
  reference the specific prior value/state being replaced. This
  includes cases that merely imply change with words like "now" or
  "currently" WITHOUT naming what came before. Example: "works at
  Google" vs "now works at Microsoft" -- the word "now" alone is
  NOT sufficient acknowledgment, because it doesn't reference Google
  specifically; classify this as CONTRADICTS, not SUPERSEDES.

- SUPERSEDES: the newer memory explicitly names or references the
  SPECIFIC prior value it is replacing, not just a generic
  transition word. Example: "lived in Delhi but moved to
  Chandigarh" (names Delhi specifically), or "used to work at
  Google, now at Microsoft" (names Google specifically).

- UNRELATED: the two memories do not make competing claims about the
  same underlying fact, even if they share a topic or category.

- CONSISTENT: the newer memory reaffirms or is fully compatible with
  the older one, with no conflict.

Special case: if the newer memory describes a single instance of
behavior that goes against a previously stated preference or habit
(e.g. one flight booking vs. a stated seating preference), treat
this as CONTRADICTS only with LOW-TO-MODERATE confidence (score
around 0.3-0.4), since a single instance does not strongly prove the
underlying preference itself has changed.

Provide a score between 0.0 and 1.0 reflecting your confidence in
the relationship (not just whether one exists), and a short,
one-sentence reasoning explaining your classification.
"""


def _format_memory(label: str, memory: Memory) -> str:
    return (
        f"{label} memory:\n"
        f"  Content: {memory.content}\n"
        f"  Category: {memory.category.value}\n"
        f"  Created at: {memory.created_at.isoformat()}\n"
    )


def detect_contradiction(
    old_memory: Memory,
    new_memory: Memory,
    model: str = MODEL_NAME,
) -> ContradictionResult:
    """
    Calls Gemini once for a single (old_memory, new_memory) pair and
    returns a validated ContradictionResult.

    model: overrides which Gemini model is called. Defaults to
    MODEL_NAME (gemini-3.6-flash), matching production behavior.
    Evaluation code may pass a different model -- e.g.
    gemini-3.5-flash-lite -- to work around gemini-3.6-flash's
    restrictive free-tier daily quota (20 requests/day, confirmed
    from a live 429 response) when running the full STALE
    evaluation over 400 pairs. This mirrors the same disclosed
    evaluation-only deviation already applied to
    classify_memory_category() in category_classifier.py.

    This function does NOT raise on failure. Any error -- network
    failure, rate limiting, malformed/unparseable response, content
    blocked by safety filters -- results in a safe fallback:
    relationship=UNRELATED, score=0.0, with the error recorded in
    `reasoning`. This guarantees scorer.py always receives a usable
    result and never has to special-case a missing contradiction
    score. A silent 0.0 fallback is a deliberate design choice: it
    means an API failure degrades gracefully to Phase-1-only
    behavior (time decay + access anomaly) rather than crashing the
    whole staleness computation for that memory.
    """
    prompt = (
        _TASK_INSTRUCTIONS
        + "\n\n"
        + _format_memory("Old", old_memory)
        + "\n"
        + _format_memory("New", new_memory)
    )

    try:
        response = _client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ContradictionResult,
                temperature=0.0,
            ),
        )
    except Exception as e:
        # Covers network errors, rate limits (ResourceExhausted),
        # auth failures, and any other API-level exception.
        return ContradictionResult(
            relationship=MemoryRelationship.UNRELATED,
            score=0.0,
            reasoning=f"API call failed: {type(e).__name__}: {e}",
        )

    if response.parsed is None:
        # response_schema validation failed, or the response was
        # empty/blocked (e.g. safety filters triggered with no
        # candidate returned).
        raw_text = getattr(response, "text", None)
        return ContradictionResult(
            relationship=MemoryRelationship.UNRELATED,
            score=0.0,
            reasoning=f"Response did not parse to schema. Raw: {raw_text!r}",
        )

    return response.parsed