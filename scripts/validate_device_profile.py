#!/usr/bin/env python3
"""validate_device_profile.py — schema + convention + source-coord + no-secret checks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolve_device as rd

# codename → expected gki_branch (from L3-qualcomm-kernel-expert SoC table)
SOC_GKI_TABLE = {
    "lahaina": "android13-5.10", "taro": "android14-5.15",
    "kalama": "android14-6.1", "sun": "android15-6.6", "crow": "android15-6.6",
}
_REQUIRED_SOURCE = ("manifest_repo", "manifest_file", "build_script")
_SECRET_KEYS = re.compile(r"(token|password|secret|api[_-]?key|private[_-]?key)", re.I)
_SECRET_VAL = re.compile(r"(ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")


def pattern_literals_present(pattern: str, branch: str) -> bool:
    """Lenient check: every non-placeholder literal of `pattern` appears in order in `branch`."""
    literals = [s for s in re.split(r"\{[^}]+\}", pattern) if s]
    pos = 0
    for lit in literals:
        idx = branch.find(lit, pos)
        if idx < 0:
            return False
        pos = idx + len(lit)
    return True


def find_secrets(node, path="") -> list[str]:
    hits = []
    if isinstance(node, dict):
        for k, val in node.items():
            if _SECRET_KEYS.search(str(k)):
                hits.append(f"{path}.{k}: secret-like key")
            hits += find_secrets(val, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits += find_secrets(item, f"{path}[{i}]")
    elif isinstance(node, str) and _SECRET_VAL.search(node):
        hits.append(f"{path}: secret-like value")
    return hits


def validate(devices_dir: Path) -> list[str]:
    errors: list[str] = []
    index = rd.load_index(devices_dir)
    for product, sku_id in rd._iter_skus(index):
        recipe = rd.load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")
        for layer in recipe.get("layers", []):
            if not rd._fragment_path(devices_dir, product, layer).exists():
                errors.append(f"{sku_id}: missing layer file {layer}")
        try:
            prof = rd.resolve_sku(devices_dir, product, sku_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sku_id}: resolve failed: {exc}")
            continue
        src = prof.get("source", {})
        for key in _REQUIRED_SOURCE:
            if not src.get(key):
                errors.append(f"{sku_id}: source.{key} missing")
        branch = recipe.get("resolves_from", {}).get("branch", "")
        pattern = prof.get("conventions", {}).get("branch_pattern", "")
        if branch and pattern and not pattern_literals_present(pattern, branch):
            errors.append(f"{sku_id}: branch '{branch}' does not match pattern '{pattern}'")
        codename = prof.get("soc", {}).get("codename")
        gki = prof.get("kernel", {}).get("gki_branch")
        if codename in SOC_GKI_TABLE and gki != SOC_GKI_TABLE[codename]:
            errors.append(f"{sku_id}: codename {codename} expects {SOC_GKI_TABLE[codename]}, got {gki}")
        errors += [f"{sku_id}: {h}" for h in find_secrets(prof)]
    return errors


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices-dir", default="devices")
    args = ap.parse_args(argv)
    errs = validate(Path(args.devices_dir))
    if errs:
        print("\n".join(errs))
        sys.exit(1)
    print("OK: all device profiles valid")


if __name__ == "__main__":
    main()
