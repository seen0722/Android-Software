#!/usr/bin/env python3
"""resolve_device.py — compose layered device profiles + resolve the active SKU."""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Maps deep-merge; scalars overridden by `override`; a None value deletes the key."""
    result = dict(base)
    for key, value in override.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


_RESERVED = {"layer"}


def load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents as a dict."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_index(devices_dir: Path) -> dict:
    """Load the devices index from index.json."""
    return json.loads((devices_dir / "index.json").read_text(encoding="utf-8"))


def _strip_meta(fragment: dict) -> dict:
    """Strip reserved metadata keys from a fragment."""
    return {k: v for k, v in fragment.items() if k not in _RESERVED}


def _fragment_path(devices_dir: Path, product: str, layer: str) -> Path:
    """Return the path to a layer fragment file."""
    rel = "base.yaml" if layer == "base" else f"{layer}.yaml"
    return devices_dir / product / rel


def resolve_sku(devices_dir: Path, product: str, sku_id: str) -> dict:
    """Compose the effective profile for a SKU by merging layers in order.

    Args:
        devices_dir: Path to the devices directory
        product: Product name (e.g., "tab-atlas")
        sku_id: SKU identifier (e.g., "atlas-lte-ofilm-cn-dl")

    Returns:
        A dict with keys: sku, resolves_from, and merged profile data.
        The 'layer' metadata key is stripped from all fragments.
    """
    # Load the SKU recipe
    sku = load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")

    # Start with empty profile and merge layers in order
    profile: dict = {}
    for layer in sku["layers"]:
        fragment = load_yaml(_fragment_path(devices_dir, product, layer))
        profile = deep_merge(profile, _strip_meta(fragment))

    # Merge any extra keys from the SKU file (excluding reserved keys)
    extras = {k: v for k, v in sku.items() if k not in {"layers", "sku", "resolves_from"}}
    profile = deep_merge(profile, extras)

    # Add sku and resolves_from to the profile
    profile["sku"] = sku["sku"]
    profile["resolves_from"] = sku.get("resolves_from", {})

    return profile


class DeviceNotFoundError(Exception):
    pass


class AmbiguousDeviceError(Exception):
    pass


def _iter_skus(index: dict):
    for product in index["products"]:
        for sku_id in product["skus"]:
            yield product["id"], sku_id


def _product_of_sku(index: dict, sku_id: str) -> str:
    for product in index["products"]:
        if sku_id in product["skus"]:
            return product["id"]
    raise DeviceNotFoundError(f"unknown sku: {sku_id}")


def _match_recipes(devices_dir: Path, index: dict, field: str, value: str):
    hits = []
    for product, sku_id in _iter_skus(index):
        recipe = load_yaml(devices_dir / product / "skus" / f"{sku_id}.yaml")
        declared = recipe.get("resolves_from", {}).get(field, "")
        if declared and (value == declared or fnmatch.fnmatch(value, declared)):
            hits.append((product, sku_id))
    return hits


def resolve_active(devices_dir: Path, *, sku=None, branch=None,
                   build_option=None, product=None) -> dict:
    index = load_index(devices_dir)
    if sku is not None:
        prof = resolve_sku(devices_dir, _product_of_sku(index, sku), sku)
        prof["_resolution"] = {"matched_by": "sku", "assumed_default": False}
        return prof
    for field, value in (("branch", branch), ("build_option", build_option)):
        if not value:
            continue
        hits = _match_recipes(devices_dir, index, field, value)
        if len(hits) == 1:
            prof = resolve_sku(devices_dir, hits[0][0], hits[0][1])
            prof["_resolution"] = {"matched_by": field, "assumed_default": False}
            return prof
        if len(hits) > 1:
            raise AmbiguousDeviceError(f"{field}={value} matches {hits}")
        raise DeviceNotFoundError(f"no SKU for {field}={value}")
    if product is not None:
        prod = next((p for p in index["products"] if p["id"] == product), None)
        if not prod:
            raise DeviceNotFoundError(f"unknown product: {product}")
        prof = resolve_sku(devices_dir, product, prod["default_sku"])
        prof["_resolution"] = {"matched_by": "default", "assumed_default": True}
        return prof
    raise AmbiguousDeviceError("no sku/branch/build_option/product cue given")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Resolve an effective device profile")
    ap.add_argument("--devices-dir", default="devices")
    ap.add_argument("--sku")
    ap.add_argument("--branch")
    ap.add_argument("--build-option")
    ap.add_argument("--product")
    args = ap.parse_args(argv)
    prof = resolve_active(Path(args.devices_dir), sku=args.sku, branch=args.branch,
                          build_option=args.build_option, product=args.product)
    print(json.dumps(prof, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
