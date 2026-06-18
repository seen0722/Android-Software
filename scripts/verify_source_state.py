#!/usr/bin/env python3
"""verify_source_state.py — confirm a synced tree matches the resolved source coords.

Two modes (auto-detected):
  - **manifest mode** — when the tree has a `.repo/` dir (a `repo`-tool managed tree of
    many git projects, e.g. an AOSP/QSSI workspace), the source identity is *which
    manifest it was synced with*, NOT a single git branch. Compare the manifest recorded
    in `.repo/manifest.xml` against the profile's expected `source.manifest_file`
    (treating `{placeholder}` version segments as wildcards).
  - **branch mode** — when there is no `.repo/` (a plain single git repo), fall back to
    comparing the checked-out branch against the SKU's `resolves_from.branch`.

Uncertainty always degrades to UNVERIFIED, never VERIFIED (Source State as Truth).
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional


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


def manifest_matches(expected: str, actual: str) -> bool:
    """True if `actual` manifest filename matches `expected`, treating `{placeholder}`
    segments in `expected` (e.g. the dated version) as `*` wildcards."""
    glob = re.sub(r"\{[^}]+\}", "*", expected)
    return fnmatch.fnmatch(actual, glob)


def _default_manifest_reader(tree_path) -> Optional[str]:
    """Return the manifest filename a `repo` tree was synced with, or None when the path
    is not a repo tree (no `.repo/`) or the manifest cannot be determined.

    Handles both repo layouts:
      - older repo: `.repo/manifest.xml` is a symlink into `manifests/<file>`
      - newer repo: `.repo/manifest.xml` is a file with `<include name="<file>"/>`
    """
    repo_dir = Path(tree_path) / ".repo"
    if not repo_dir.exists():
        return None
    manifest_xml = repo_dir / "manifest.xml"
    try:
        if manifest_xml.is_symlink():
            return os.path.basename(os.readlink(manifest_xml))
        if manifest_xml.exists():
            text = manifest_xml.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'<include\s+name="([^"]+)"', text)
            if match:
                return match.group(1)
    except OSError:
        return None
    return None


def _default_runner(cmd) -> Optional[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def verify(profile: dict, tree_path, runner: Callable = _default_runner,
           manifest_reader: Callable = _default_manifest_reader) -> dict:
    src = profile.get("source", {})
    dev_manifest = src.get("manifest_file", "")          # daily-dev sync (e.g. default.xml)
    release_manifest = src.get("release_manifest", "")   # pinned release snapshot
    expected_branch = profile.get("resolves_from", {}).get("branch", "")
    hint = render_fetch_hint(profile)

    actual_manifest = manifest_reader(tree_path)
    if actual_manifest is not None:
        # manifest mode — repo-managed tree. BOTH a daily-dev sync (default.xml) and a
        # pinned release manifest are legitimate; tag which one (manifest_kind).
        accepted = [m for m in (dev_manifest, release_manifest) if m]
        kind: Optional[str] = None
        if dev_manifest and manifest_matches(dev_manifest, actual_manifest):
            kind = "dev"
        elif release_manifest and manifest_matches(release_manifest, actual_manifest):
            kind = "release"
        if not accepted:
            state = "UNVERIFIED"
        elif kind is not None:
            state = "VERIFIED"
        else:
            state = "MISMATCH"
        return {"state": state, "mode": "manifest", "manifest_kind": kind,
                "expected_manifests": accepted, "actual_manifest": actual_manifest,
                "expected_branch": expected_branch, "actual_branch": None,
                "fetch_hint": hint}

    # branch mode — plain single git repo
    actual_branch = runner(["git", "-C", str(tree_path), "rev-parse", "--abbrev-ref", "HEAD"])
    if actual_branch is None or actual_branch == "":
        state = "UNVERIFIED"
    elif actual_branch == expected_branch:
        state = "VERIFIED"
    else:
        state = "MISMATCH"
    return {"state": state, "mode": "branch", "manifest_kind": None,
            "expected_manifests": [m for m in (dev_manifest, release_manifest) if m],
            "actual_manifest": None,
            "expected_branch": expected_branch, "actual_branch": actual_branch,
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
