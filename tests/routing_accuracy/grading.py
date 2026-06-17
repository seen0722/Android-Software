"""
grading.py — Shared routing-decision grader
============================================
Single source of truth for how a routing decision is scored against the
ground-truth TEST_CASES. BOTH runners import this:

  - test_router.py   (mock/deterministic route_task, mode="live")
  - llm_runner.py    (real LLM routing decision, mode="llm")

Sharing one grader is the whole point: only when the mock score and the LLM
score are produced by the SAME comparison can the gap between them be
attributed to "LLM reasoning != regex", rather than to a difference in how
the two runs were judged.

Grading policy (decided in the design review):
  - PRIMARY metric is the skill match. "primary hit == pass" — the agent's
    primary L2 skill must equal expected_skill. Extra secondary skills the
    agent may list are neither required nor penalized.
  - paths_match is recorded as a SECONDARY signal only; it never flips
    PASS/FAIL on its own. This mirrors the original run_tests() behavior
    (test_router.py line 1400-1401).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class GradeResult:
    skill_match: bool          # primary metric — drives PASS/FAIL
    paths_match: bool          # secondary signal — recorded, never decides
    status: str                # "PASS" | "FAIL"


def skill_matches(got_skill: Optional[str], expected_skill: str) -> bool:
    """Primary metric: exact match of the primary L2 skill."""
    return got_skill == expected_skill


def _path_covered(got_paths: List[str], expected_path: str) -> bool:
    """
    Is a single expected path covered by any returned path?

    Behavior is lifted verbatim from the original run_tests() loop
    (test_router.py lines 1380-1399) so the refactor changes nothing:
      1. Bidirectional prefix match (gp.startswith(ep) or ep.startswith(gp))
      2. Leading-glob entries like "*.rc"  -> suffix match
      3. Embedded wildcards like "vendor/*/sepolicy/" -> regex match
    """
    for gp in got_paths:
        if gp.startswith(expected_path) or expected_path.startswith(gp):
            return True
        # Handle glob patterns in expected_paths (e.g., "*.rc")
        if expected_path.startswith("*"):
            if gp.endswith(expected_path[1:]):
                return True
        # Handle wildcards in expected paths (e.g., "vendor/*/sepolicy/")
        if "*" in expected_path:
            pat = expected_path.replace("*", "[^/]+")
            if re.match(pat, gp):
                return True
    return False


def paths_match(got_paths: List[str], expected_paths: List[str]) -> bool:
    """Secondary signal: every expected path is covered by some returned path."""
    got = got_paths or []
    return all(_path_covered(got, ep) for ep in expected_paths)


def grade(
    got_skill: Optional[str],
    got_paths: List[str],
    expected_skill: str,
    expected_paths: List[str],
) -> GradeResult:
    """Grade one routing decision. PASS iff the primary skill matches."""
    sm = skill_matches(got_skill, expected_skill)
    pm = paths_match(got_paths, expected_paths)
    return GradeResult(skill_match=sm, paths_match=pm, status="PASS" if sm else "FAIL")
