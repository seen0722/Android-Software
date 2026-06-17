"""
llm_runner.py — Real LLM end-to-end routing eval (Layer A)
==========================================================
Replaces the deterministic route_task() mock with a real LLM that READS the
L1 router SKILL.md and emits an [L1 ROUTING DECISION] block, which we parse
and grade with the SAME grader the mock uses (grading.grade).

What this measures: does Claude, reasoning over the L1 skill spec, route a
task to the correct primary L2 skill? (Layer A — routing only. Not L2 answer
quality.)

Design anchors (from the approved design):
  - Inject ONLY the L1 SKILL.md (agents route from L1 alone). No candidate
    list in the prompt — that would turn routing into multiple choice.
  - Only the task description reaches the model. notes/expected_* never do.
  - Non-determinism is the point: sample k times, report pass@1 (expected),
    majority-vote accuracy, and per-case consistency.
  - PASS/FAIL = primary skill match (shared grading.grade()).

Transport: Python stdlib urllib → Anthropic Messages REST API. No SDK to
install; set ANTHROPIC_API_KEY and run. Use --dry-run (no key, no network)
to exercise the prompt/parse/grade pipeline against the mock router.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 tests/routing_accuracy/llm_runner.py --variant clued --k 5
    python3 tests/routing_accuracy/llm_runner.py --variant both  --k 5 --model claude-haiku-4-5-20251001
    python3 tests/routing_accuracy/llm_runner.py --dry-run --variant both   # no API
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from grading import grade  # noqa: E402
from test_router import TEST_CASES  # noqa: E402  (reuse the single ground-truth)

L1_SKILL_PATH = REPO_ROOT / "skills" / "L1-aosp-root-router" / "SKILL.md"
STRIPPED_PATH = HERE / "stripped_cases.json"
RESULTS_DIR = HERE / "results"

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # routing is classification; Haiku suffices
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 512
TEMPERATURE = 0.3  # low but non-zero: 0 would hide real deployment drift

# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def load_l1_skill() -> str:
    return L1_SKILL_PATH.read_text(encoding="utf-8")


def build_prompt(description: str, l1_skill: str) -> str:
    """Inject the L1 spec, give the task, demand ONLY the decision block."""
    return (
        "You are the AOSP Root Router (Layer 1). Below is your routing "
        "specification, verbatim.\n\n"
        "=== L1-aosp-root-router/SKILL.md ===\n"
        f"{l1_skill}\n"
        "=== END SKILL.md ===\n\n"
        "Route the following user task by applying the specification above.\n\n"
        f'User task: "{description}"\n\n'
        "Respond with ONLY the [L1 ROUTING DECISION] block exactly as defined "
        "in the Handoff Rules section (the fields Intent / Path(s) / L2 Skill / "
        "Reason). Output nothing before or after the block."
    )


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

# A skill token looks like L2-kernel-gki-expert or L3-qualcomm-kernel-expert.
_SKILL_RE = re.compile(r"(L[23]-[a-z0-9]+(?:-[a-z0-9]+)*-expert)", re.IGNORECASE)
_SKILL_LINE_RE = re.compile(r"L2\s*Skill\s*:?\s*(.+)", re.IGNORECASE)
_PATHS_LINE_RE = re.compile(r"Path\(s\)\s*:?\s*(.+)", re.IGNORECASE)


def parse_routing_decision(text: str) -> Dict[str, object]:
    """
    Extract {skill, paths, parse_error} from a model response.

    Parse failure (no skill token found) is itself a FAIL, not a discard:
    not emitting a parseable decision block is a routing-protocol defect.
    """
    skill: Optional[str] = None
    m_line = _SKILL_LINE_RE.search(text)
    if m_line:
        m_tok = _SKILL_RE.search(m_line.group(1))
        if m_tok:
            skill = m_tok.group(1)
    if skill is None:  # fallback: first skill token anywhere in the response
        m_any = _SKILL_RE.search(text)
        if m_any:
            skill = m_any.group(1)

    paths: List[str] = []
    m_paths = _PATHS_LINE_RE.search(text)
    if m_paths:
        raw = m_paths.group(1).strip()
        raw = raw.strip("`*").strip()
        for tok in re.split(r"[,\s]+", raw):
            tok = tok.strip("`*.,;").strip()
            if tok and ("/" in tok or tok.startswith("*") or tok.endswith(".bp") or tok.endswith(".mk")):
                paths.append(tok)

    return {"skill": skill, "paths": paths, "parse_error": skill is None}


# ---------------------------------------------------------------------------
# Model call (urllib; no SDK) + dry-run fallback
# ---------------------------------------------------------------------------

@dataclass
class CallResult:
    text: str
    in_tokens: int
    out_tokens: int


def call_anthropic(prompt: str, model: str, api_key: str) -> CallResult:
    body = json.dumps({
        "model": model,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", API_VERSION)
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in payload.get("content", []))
    usage = payload.get("usage", {})
    return CallResult(text, usage.get("input_tokens", 0), usage.get("output_tokens", 0))


def synth_decision_block(description: str) -> str:
    """Dry-run only: synthesize a decision block from the mock router so the
    parse+grade pipeline can be exercised end-to-end without the API."""
    from test_router import route_task
    r = route_task(description)
    paths = ", ".join(r.get("paths") or []) or "(none)"
    return (
        "[L1 ROUTING DECISION]\n"
        f"Intent: {description[:50]}\n"
        f"Path(s): {paths}\n"
        f"L2 Skill: {r.get('skill')}\n"
        "Reason: dry-run synthesized from mock route_task()\n"
        "[END ROUTING → loading L2 skill now]"
    )


# ---------------------------------------------------------------------------
# Case loading (clued vs stripped variants)
# ---------------------------------------------------------------------------

@dataclass
class Case:
    id: str
    description: str
    expected_skill: str
    expected_paths: List[str]
    variant: str                 # "clued" | "stripped"
    undecidable: bool = False    # stripped-only: not counted in main accuracy


def load_cases(variant: str) -> List[Case]:
    by_id = {tc.id: tc for tc in TEST_CASES}
    if variant == "clued":
        return [Case(tc.id, tc.description, tc.expected_skill, list(tc.expected_paths), "clued")
                for tc in TEST_CASES]
    if variant == "stripped":
        if not STRIPPED_PATH.exists():
            sys.exit(f"ERROR: {STRIPPED_PATH.name} not found — build the stripped subset first.")
        data = json.loads(STRIPPED_PATH.read_text(encoding="utf-8"))
        cases: List[Case] = []
        for row in data["cases"]:
            tc = by_id.get(row["id"])
            if not tc:
                continue
            cases.append(Case(
                tc.id, row["description_stripped"], tc.expected_skill,
                list(tc.expected_paths), "stripped", bool(row.get("undecidable_when_stripped", False)),
            ))
        return cases
    raise ValueError(f"unknown variant: {variant}")


# ---------------------------------------------------------------------------
# Sampling + metrics
# ---------------------------------------------------------------------------

@dataclass
class CaseOutcome:
    id: str
    variant: str
    expected_skill: str
    samples: List[Optional[str]]   # predicted skill per sample (None = parse fail)
    pass_count: int                # samples graded PASS
    k: int
    parse_failures: int
    undecidable: bool

    @property
    def pass_at_1(self) -> float:          # expected single-shot accuracy
        return self.pass_count / self.k if self.k else 0.0

    @property
    def majority_correct(self) -> bool:    # modal prediction is correct
        votes = [s for s in self.samples if s is not None]
        if not votes:
            return False
        modal, _ = Counter(votes).most_common(1)[0]
        return modal == self.expected_skill

    @property
    def modal_fraction(self) -> float:     # consistency: modal share over k
        if not self.samples:
            return 0.0
        modal_count = Counter(self.samples).most_common(1)[0][1]
        return modal_count / self.k

    @property
    def distinct_skills(self) -> int:
        return len(set(self.samples))


def run_variant(cases: List[Case], k: int, model: str, dry_run: bool,
                api_key: Optional[str], l1_skill: str) -> List[CaseOutcome]:
    outcomes: List[CaseOutcome] = []
    total_in = total_out = 0
    for idx, c in enumerate(cases, 1):
        samples: List[Optional[str]] = []
        pass_count = parse_failures = 0
        for _ in range(k):
            if dry_run:
                text = synth_decision_block(c.description)
            else:
                prompt = build_prompt(c.description, l1_skill)
                try:
                    res = call_anthropic(prompt, model, api_key)
                    text = res.text
                    total_in += res.in_tokens
                    total_out += res.out_tokens
                except urllib.error.HTTPError as e:
                    text = ""
                    print(f"  ! HTTP {e.code} on {c.id}: {e.read().decode('utf-8', 'ignore')[:160]}")
                    time.sleep(2)
            parsed = parse_routing_decision(text)
            if parsed["parse_error"]:
                parse_failures += 1
            g = grade(parsed["skill"], parsed["paths"], c.expected_skill, c.expected_paths)
            if g.status == "PASS":
                pass_count += 1
            samples.append(parsed["skill"])
        outcomes.append(CaseOutcome(c.id, c.variant, c.expected_skill, samples,
                                    pass_count, k, parse_failures, c.undecidable))
        print(f"  [{idx:>3}/{len(cases)}] {c.id} ({c.variant}): "
              f"pass@1={pass_count}/{k}  modal={samples and Counter(samples).most_common(1)[0][0]}")
    if not dry_run:
        print(f"  tokens: in={total_in} out={total_out}")
    return outcomes


def summarize(outcomes: List[CaseOutcome], label: str) -> Dict[str, object]:
    counted = [o for o in outcomes if not o.undecidable]
    n = len(counted)
    pass_at_1 = sum(o.pass_at_1 for o in counted) / n if n else 0.0
    majority = sum(1 for o in counted if o.majority_correct) / n if n else 0.0
    total_samples = sum(o.k for o in counted)
    parse_fail_rate = sum(o.parse_failures for o in counted) / total_samples if total_samples else 0.0
    low_consistency = [o.id for o in counted if o.modal_fraction < 0.6]
    worst = [o.id for o in counted if o.pass_at_1 < 0.5]
    excluded = [o.id for o in outcomes if o.undecidable]

    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(f"  cases scored:        {n}  (excluded undecidable: {len(excluded)})")
    print(f"  pass@1 (expected):   {pass_at_1 * 100:.1f}%")
    print(f"  majority-vote:       {majority * 100:.1f}%")
    print(f"  parse-failure rate:  {parse_fail_rate * 100:.1f}%")
    print(f"  low-consistency ids: {low_consistency or '—'}")
    print(f"  pass@1<0.5 ids:      {worst or '—'}")
    if excluded:
        print(f"  excluded (undecidable): {excluded}")
    return {
        "label": label, "n": n, "pass_at_1": pass_at_1, "majority": majority,
        "parse_fail_rate": parse_fail_rate, "low_consistency": low_consistency,
        "worst": worst, "excluded": excluded,
        "per_case": [asdict(o) for o in outcomes],
    }


def report_clued_vs_stripped(clued: List[CaseOutcome], stripped: List[CaseOutcome]) -> None:
    """The headline of this whole exercise: dependence on keyword clues."""
    cs = {o.id: o for o in stripped if not o.undecidable}
    overlap = [(o, cs[o.id]) for o in clued if o.id in cs]
    if not overlap:
        return
    print(f"\n{'=' * 70}\nCLUED vs STRIPPED (same {len(overlap)} cases)\n{'=' * 70}")
    print(f"  {'id':<9} {'clued p@1':>10} {'stripped p@1':>14}  delta")
    drops = []
    for cl, st in overlap:
        d = st.pass_at_1 - cl.pass_at_1
        drops.append(d)
        flag = "  <-- big drop" if d <= -0.4 else ""
        print(f"  {cl.id:<9} {cl.pass_at_1 * 100:>9.0f}% {st.pass_at_1 * 100:>13.0f}%  {d * 100:+.0f}pp{flag}")
    avg = sum(drops) / len(drops)
    print(f"\n  avg stripped delta: {avg * 100:+.1f}pp  "
          f"({'robust semantic routing' if avg > -0.15 else 'likely keyword-dependent'})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="LLM e2e routing eval (Layer A)")
    ap.add_argument("--variant", choices=["clued", "stripped", "both"], default="clued")
    ap.add_argument("--k", type=int, default=5, help="samples per case")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=0, help="cap cases (smoke test)")
    ap.add_argument("--cases", default="", help="comma-separated case ids, e.g. TC-001,TC-003")
    ap.add_argument("--dry-run", action="store_true", help="no API; synth from mock router")
    ap.add_argument("--out", default="", help="write results JSON to this path")
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not args.dry_run and not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set. Set it, or use --dry-run to test the pipeline.")

    l1_skill = "" if args.dry_run else load_l1_skill()
    variants = ["clued", "stripped"] if args.variant == "both" else [args.variant]

    def _filter(cases: List[Case]) -> List[Case]:
        if args.cases:
            want = {c.strip() for c in args.cases.split(",")}
            cases = [c for c in cases if c.id in want]
        if args.limit:
            cases = cases[: args.limit]
        return cases

    all_summaries = {}
    outcomes_by_variant: Dict[str, List[CaseOutcome]] = {}
    for v in variants:
        cases = _filter(load_cases(v))
        print(f"\n>>> variant={v}  cases={len(cases)}  k={args.k}  "
              f"model={'(dry-run)' if args.dry_run else args.model}")
        oc = run_variant(cases, args.k, args.model, args.dry_run, api_key, l1_skill)
        outcomes_by_variant[v] = oc
        all_summaries[v] = summarize(oc, f"variant={v}")

    if "clued" in outcomes_by_variant and "stripped" in outcomes_by_variant:
        report_clued_vs_stripped(outcomes_by_variant["clued"], outcomes_by_variant["stripped"])

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "model": args.model, "k": args.k, "dry_run": args.dry_run,
            "summaries": all_summaries,
        }, indent=2), encoding="utf-8")
        print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
