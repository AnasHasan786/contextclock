"""
Run hand-written memory pairs through the contradiction detector and compare
each verdict with what the detector's prompt says it should be.

    python scripts/try_pairs.py --dry-run             # list the cases, 0 requests
    python scripts/try_pairs.py --category employment # one category
    python scripts/try_pairs.py --only E1 E2 PF5      # specific cases
    python scripts/try_pairs.py                       # all cases, 1 request each

Every case is ONE Gemini request. The default model is the one your STALE
evaluation used (gemini-3.5-flash-lite), not the production default, because
gemini-3.6-flash allows only 20 requests a day on the free tier.

The expected verdicts come from the rules in the detector's prompt, not from
ground truth. Cases marked borderline are judgment calls: a different answer
is reported as OFF (read the reasoning), never as FAIL.
"""

import argparse
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CONFLICT = ("CONTRADICTS", "SUPERSEDES")
NO_CONFLICT = ("UNRELATED", "CONSISTENT")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    old: str
    new: str
    ok: tuple[str, ...]  # relationships accepted
    lo: float = 0.0  # score bounds, applied only when the verdict is a conflict
    hi: float = 1.0
    borderline: bool = False
    note: str = ""
    new_category: str | None = None  # defaults to `category`


CASES: list[Case] = [
    # ---------------------------------------------------------------- employment
    Case("E1", "employment", "User works at Google.", "User now works at Microsoft.",
         ("CONTRADICTS",), lo=0.7,
         note="'now' alone does not name Google, so CONTRADICTS, not SUPERSEDES."),
    Case("E2", "employment", "User works at Google.",
         "User used to work at Google but now works at Microsoft.",
         ("SUPERSEDES",), lo=0.7, note="Names Google explicitly."),
    Case("E3", "employment", "User works at Google.",
         "User is employed at Google as a software engineer.",
         ("CONSISTENT",), note="Reaffirms with extra detail."),
    Case("E4", "employment", "User works at Google.", "User commutes to the office by metro.",
         NO_CONFLICT, note="Same topic, different fact."),
    Case("E5", "employment", "User always works from the office.", "User worked from home today.",
         ("CONTRADICTS",), lo=0.2, hi=0.5,
         note="One instance against a habit. The prompt asks for about 0.3 to 0.4."),
    Case("E6", "employment", "User is a software engineer at Google.",
         "User was promoted to senior software engineer at Google.",
         ("SUPERSEDES", "CONTRADICTS", "CONSISTENT"), lo=0.3, borderline=True,
         note="Title changes, employer does not. Any of the three is defensible."),
    Case("E7", "employment", "User works at Google.", "User was laid off from Google last month.",
         CONFLICT, lo=0.7, borderline=True,
         note="No new employer, but Google is named."),

    # ------------------------------------------------------------------ location
    Case("L1", "location", "User lives in Delhi.", "User now lives in Chandigarh.",
         ("CONTRADICTS",), lo=0.7),
    Case("L2", "location", "User lives in Delhi.", "User moved from Delhi to Chandigarh.",
         ("SUPERSEDES",), lo=0.7),
    Case("L3", "location", "User lives in Chandigarh.", "User's home is in Chandigarh.",
         ("CONSISTENT",)),
    Case("L4", "location", "User lives in Delhi.", "User owns a two-bedroom flat.", NO_CONFLICT),
    Case("L5", "location", "User lives in Delhi.", "User is on a two-week trip to Goa.",
         NO_CONFLICT + ("CONTRADICTS",), hi=0.5,
         note="A trip is not a move. A conflict score above 0.5 is a false positive."),
    Case("L6", "location", "User lives in Delhi.", "User is moving to Berlin next month.",
         NO_CONFLICT + ("CONTRADICTS",), hi=0.6, borderline=True,
         note="A future change. The present state is still Delhi."),

    # -------------------------------------------------------------- relationship
    Case("R1", "relationship", "User is single.", "User is now engaged to Priya.",
         ("CONTRADICTS",), lo=0.7),
    Case("R2", "relationship", "User is dating Priya.",
         "User broke up with Priya and is now dating Neha.", ("SUPERSEDES",), lo=0.7),
    Case("R3", "relationship", "User is married to Priya.",
         "User celebrated their wedding anniversary with Priya.", ("CONSISTENT",)),
    Case("R4", "relationship", "User is married to Priya.", "User's brother lives in Canada.",
         NO_CONFLICT),
    Case("R5", "relationship", "User calls his mother every Sunday.",
         "User skipped the call with his mother this Sunday.",
         ("CONTRADICTS",), lo=0.2, hi=0.5, note="One instance against a habit."),
    Case("R6", "relationship", "User's best friend is Rahul.", "User's best friend is Amit.",
         CONFLICT, lo=0.5, borderline=True,
         note="A singular slot, but people can have several best friends."),

    # ---------------------------------------------------------------- preference
    Case("PF1", "preference", "User prefers window seats on flights.",
         "User now prefers aisle seats.", ("CONTRADICTS",), lo=0.7),
    Case("PF2", "preference", "User prefers window seats on flights.",
         "User used to prefer window seats but now prefers aisle seats.",
         ("SUPERSEDES",), lo=0.7),
    Case("PF3", "preference", "User prefers window seats on flights.",
         "User always picks a window seat when flying.", ("CONSISTENT",)),
    Case("PF4", "preference", "User prefers window seats on flights.", "User likes vegetarian food.",
         NO_CONFLICT),
    Case("PF5", "preference", "User prefers window seats on flights.",
         "User booked an aisle seat on the flight to Mumbai.",
         ("CONTRADICTS",), lo=0.2, hi=0.5,
         note="The example from your prompt: one booking is weak evidence."),
    Case("PF6", "preference", "User dislikes coffee.", "User loves coffee.",
         CONFLICT, lo=0.7, note="Direct opposites."),

    # ------------------------------------------------------------------ personal
    Case("PE1", "personal", "User has a dog named Bruno.", "User does not have any pets.",
         ("CONTRADICTS",), lo=0.7),
    Case("PE2", "personal", "User plays cricket every weekend.",
         "User stopped playing cricket and took up badminton instead.",
         ("SUPERSEDES",), lo=0.7),
    Case("PE3", "personal", "User plays cricket every weekend.", "User captains a local cricket team.",
         ("CONSISTENT",)),
    Case("PE4", "personal", "User plays cricket every weekend.", "User has a younger sister.",
         NO_CONFLICT),
    Case("PE5", "personal", "User goes for a run every morning.", "User skipped their run today.",
         ("CONTRADICTS",), lo=0.2, hi=0.5, note="One instance against a habit."),
    Case("PE6", "personal", "User is 24 years old.", "User is 25 years old.",
         CONFLICT + ("CONSISTENT",), lo=0.3, borderline=True,
         note="Ages change on their own, so a careful model may call this consistent."),

    # ---------------------------------------------------------------------- fact
    Case("F1", "fact", "User's company has 50 employees.", "User's company now has 200 employees.",
         ("CONTRADICTS",), lo=0.7),
    Case("F2", "fact", "User's phone is an iPhone 13.",
         "User upgraded from the iPhone 13 to an iPhone 16.", ("SUPERSEDES",), lo=0.7),
    Case("F3", "fact", "User owns a Honda Civic.", "User drives a Honda Civic to work.",
         ("CONSISTENT",)),
    Case("F4", "fact", "User owns a Honda Civic.", "User's flat has a balcony.", NO_CONFLICT),
    Case("F5", "fact", "User usually takes the metro to work.", "User took a cab to work today.",
         ("CONTRADICTS",), lo=0.2, hi=0.5, note="One instance against a habit."),
    Case("F6", "fact", "User owns a Honda Civic.", "User bought a Toyota Fortuner.",
         NO_CONFLICT + ("CONTRADICTS",), hi=0.5, borderline=True,
         note="Additive: owning both is possible."),

    # ------------------------------------------------------- general / robustness
    Case("G1", "preference", "User is vegetarian.", "User eats chicken biryani regularly.",
         CONFLICT, lo=0.7, note="Conflict with no shared keyword."),
    Case("G2", "location", "User lives in Delhi.", "User resides in Delhi.", ("CONSISTENT",),
         note="Paraphrase."),
    Case("G3", "location", "User lives in Delhi.", "User's home address is in Pune.",
         CONFLICT, lo=0.6, new_category="fact",
         note="Conflict across categories. Retrieval must not filter these out."),
    Case("G4", "employment", "User works at Google.", "User works at Google.", ("CONSISTENT",),
         note="Identical text."),
    Case("G5", "employment", "User worked at Google in 2019.", "User works at Microsoft.",
         NO_CONFLICT, borderline=True,
         note="A past job and a current job are compatible. A conflict here is a false positive."),
    Case("G6", "employment", "User works at Google.", "ok thanks", ("UNRELATED",),
         note="Noise."),
    Case("G7", "employment", "User lives in Delhi and works at Google.",
         "User now works at Microsoft but still lives in Delhi.",
         CONFLICT, lo=0.5, borderline=True,
         note="Compound: the job changed, the city did not."),
]


def judge(case: Case, relationship: str, score: float, lenient: bool) -> bool:
    accepted = set(case.ok)
    if lenient and accepted & set(CONFLICT):
        accepted |= set(CONFLICT)
    if relationship not in accepted:
        return False
    if relationship in CONFLICT and not (case.lo <= score <= case.hi):
        return False
    return True


def expectation(case: Case) -> str:
    rel = "/".join(case.ok)
    if set(case.ok) & set(CONFLICT) and (case.lo > 0.0 or case.hi < 1.0):
        return f"{rel} [{case.lo:.1f}-{case.hi:.1f}]"
    return rel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--category", help="run one category, e.g. employment")
    parser.add_argument("--only", nargs="+", metavar="ID", help="run only these case ids")
    parser.add_argument("--delay", type=float, default=4.0, help="seconds between requests")
    parser.add_argument("--lenient", action="store_true", help="accept CONTRADICTS and SUPERSEDES interchangeably")
    parser.add_argument("--dry-run", action="store_true", help="list the cases without calling Gemini")
    args = parser.parse_args()

    cases = [
        c for c in CASES
        if (args.category is None or c.category == args.category)
        and (args.only is None or c.id in args.only)
    ]
    if not cases:
        print("No cases match.")
        return 1

    if args.dry_run:
        for c in cases:
            print(f"{c.id:<4} {c.category:<13} {expectation(c):<32} {c.old}  ->  {c.new}")
        print(f"\n{len(cases)} cases. A real run makes {len(cases)} Gemini requests.")
        return 0

    from app.core.contradiction import detect_contradiction
    from app.core.fallback import is_fallback
    from app.models.memory import Memory, MemoryCategory

    print(f"{len(cases)} cases on {args.model}, {args.delay:g}s apart ({len(cases)} requests)\n")
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like the models
    tally: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    errors: list[str] = []
    failed = False

    for index, case in enumerate(cases):
        old = Memory(id=f"{case.id}-old", content=case.old, category=MemoryCategory(case.category),
                     user_id="try", agent_id="try", created_at=now - timedelta(days=30))
        new = Memory(id=f"{case.id}-new", content=case.new,
                     category=MemoryCategory(case.new_category or case.category),
                     user_id="try", agent_id="try", created_at=now)

        result = detect_contradiction(old_memory=old, new_memory=new, model=args.model)

        if is_fallback(result):
            verdict = "ERROR"
            errors.append(case.id)
        elif judge(case, result.relationship.value, result.score, args.lenient):
            verdict = "PASS"
        elif case.borderline:
            verdict = "OFF"
        else:
            verdict = "FAIL"
            failed = True
        tally[case.category][verdict] += 1

        print(f"{verdict:<5} {case.id:<4} {result.relationship.value:<11} {result.score:.2f}   "
              f"{case.old}  ->  {case.new}", flush=True)
        if verdict in ("FAIL", "OFF"):
            print(f"        expected {expectation(case)}")
            print(f"        {result.reasoning}")
            if case.note:
                print(f"        note: {case.note}")
        elif verdict == "ERROR":
            print(f"        {result.reasoning[:160]}")

        if index < len(cases) - 1 and args.delay > 0:
            time.sleep(args.delay)

    print("\nSummary (PASS / FAIL / OFF = borderline miss / ERROR = call failed, not counted)")
    for category, counts in tally.items():
        print(f"  {category:<13} {counts['PASS']} / {counts['FAIL']} / {counts['OFF']} / {counts['ERROR']}")
    if errors:
        print(f"\nRe-run the failed calls: python scripts/try_pairs.py --only {' '.join(errors)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())