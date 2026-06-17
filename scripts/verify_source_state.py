#!/usr/bin/env python3
"""verify_source_state.py — compare a synced tree against the resolved source coords."""
from __future__ import annotations

import subprocess
from pathlib import Path


def render_fetch_hint(profile: dict) -> str:
    src = profile.get("source", {})
    fetch = src.get("fetch", {})
    branch = profile.get("resolves_from", {}).get("branch", "")
    subs = {
        "manifest_repo": src.get("manifest_repo", ""),
        "manifest_file": src.get("manifest_file", ""),
        "branch": branch,
    }

    def fill(template: str) -> str:
        for key, val in subs.items():
            template = template.replace("{" + key + "}", val)
        return template

    lines = [f"# GitLab location: {src.get('gitlab_location', 'n/a')}"]
    if fetch.get("init"):
        lines.append(fill(fetch["init"]))
    if fetch.get("sync"):
        lines.append(fill(fetch["sync"]))
    return "\n".join(lines)


def _default_runner(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def verify(profile: dict, tree_path: Path, runner=_default_runner) -> dict:
    expected = profile.get("resolves_from", {}).get("branch", "")
    actual = runner(["git", "-C", str(tree_path), "rev-parse", "--abbrev-ref", "HEAD"])
    hint = render_fetch_hint(profile)
    if actual is None or actual == "":
        state = "UNVERIFIED"
    elif actual == expected:
        state = "VERIFIED"
    else:
        state = "MISMATCH"
    return {"state": state, "expected_branch": expected, "actual_branch": actual,
            "fetch_hint": hint}


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("tree_path")
    ap.add_argument("--profile", required=True, help="path to a resolved profile JSON")
    args = ap.parse_args(argv)
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    out = verify(profile, Path(args.tree_path))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["state"] == "VERIFIED" else 2)


if __name__ == "__main__":
    main()
